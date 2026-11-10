"""Authentication and session business logic.

Design notes
------------
* Passwords are verified with Argon2id and never stored or logged in plaintext.
* Sessions are database-backed opaque handles. Only SHA-256 token hashes are
  stored, so the raw cookie value is required to use a session.
* Login failures use a single generic error for unknown emails, wrong
  passwords, inactive accounts and locked accounts to prevent account
  enumeration.
* Per-account lockout is persisted in the ``users`` table, so it survives
  process restarts and works across multiple workers.
"""

from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    constant_time_compare,
    dummy_password_hash,
    generate_csrf_token,
    generate_session_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    utcnow,
    validate_password_strength,
    verify_password,
)
from app.models.auth_session import AuthSession
from app.models.enums import UserRole
from app.models.user import User

GENERIC_AUTH_ERROR = "Invalid email or password."
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_VALID_ROLES = {role.value for role in UserRole}


class AuthenticationError(Exception):
    """Generic authentication failure, safe to expose to clients."""


class InvalidEmailError(ValueError):
    """Raised when an email address is malformed."""


class EmailAlreadyExistsError(ValueError):
    """Raised when an account already uses the requested email address."""


class AdminAccountError(ValueError):
    """Raised when the target account is missing or is not an administrator."""


class InvalidSessionError(Exception):
    """Raised when a session cookie is missing, expired or revoked."""


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if len(normalized) > 255 or not _EMAIL_RE.match(normalized):
        raise InvalidEmailError("Enter a valid email address.")
    return normalized


def _normalize_role(role: UserRole | str) -> str:
    value = role.value if isinstance(role, UserRole) else str(role)
    if value not in _VALID_ROLES:
        raise ValueError(f"Unsupported role: {value}")
    return value


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    role: UserRole | str = UserRole.viewer,
    is_active: bool = True,
) -> User:
    """Create a user with an Argon2id password hash."""
    normalized_email = _validate_email(email)
    validate_password_strength(password)

    existing_id = db.scalar(select(User.id).where(User.email == normalized_email))
    if existing_id is not None:
        raise EmailAlreadyExistsError("An account with that email already exists.")

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        role=_normalize_role(role),
        is_active=is_active,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyExistsError(
            "An account with that email already exists."
        ) from exc
    db.refresh(user)
    return user


def update_admin_credentials(
    db: Session,
    *,
    current_email: str,
    new_email: str,
    new_password: str,
) -> User:
    """Update an existing administrator's email and Argon2id password."""
    normalized_current = normalize_email(current_email)
    normalized_new = _validate_email(new_email)
    validate_password_strength(new_password)

    user = db.scalar(select(User).where(User.email == normalized_current))
    if user is None or user.role != UserRole.admin.value:
        raise AdminAccountError("Administrator account not found.")

    duplicate_id = db.scalar(
        select(User.id).where(
            User.email == normalized_new,
            User.id != user.id,
        )
    )
    if duplicate_id is not None:
        raise EmailAlreadyExistsError("An account with that email already exists.")

    user.email = normalized_new
    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None

    # Password/email changes invalidate all existing sessions for this admin.
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
        .execution_options(synchronize_session=False)
    )

    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyExistsError(
            "An account with that email already exists."
        ) from exc

    db.refresh(user)
    return user


def _record_failed_login(db: Session, user: User, now) -> None:
    settings = get_settings()
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= settings.login_max_failures:
        user.failed_login_count = 0
        user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
    db.add(user)
    db.commit()


def authenticate_user(db: Session, email: str, password: str) -> User:
    """Authenticate a user or raise a generic ``AuthenticationError``.

    The password hash is verified even for unknown, inactive or locked
    accounts so response timing does not reveal whether an email exists.
    """
    settings = get_settings()
    normalized_email = normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized_email))
    now = utcnow()

    if user is None:
        verify_password(dummy_password_hash(), password or "")
        raise AuthenticationError(GENERIC_AUTH_ERROR)

    if user.locked_until is not None and user.locked_until > now:
        verify_password(user.password_hash, password or "")
        raise AuthenticationError(GENERIC_AUTH_ERROR)

    password_ok = verify_password(user.password_hash, password or "")
    if not password_ok or not user.is_active:
        _record_failed_login(db, user, now)
        raise AuthenticationError(GENERIC_AUTH_ERROR)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_session(
    db: Session,
    user: User,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[AuthSession, str, str]:
    """Create a session and return ``(record, raw_token, raw_csrf_token)``."""
    settings = get_settings()
    token = generate_session_token()
    csrf_token = generate_csrf_token()
    now = utcnow()

    session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token_hash=hash_token(csrf_token),
        created_at=now,
        expires_at=now + timedelta(minutes=settings.session_ttl_minutes),
        last_seen_at=now,
        ip_address=(ip_address or "").strip()[:64] or None,
        user_agent=(user_agent or "").strip()[:255] or None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, token, csrf_token


def get_active_session(db: Session, raw_token: str) -> AuthSession:
    """Return a valid, unexpired session or raise ``InvalidSessionError``."""
    if not raw_token:
        raise InvalidSessionError("Missing session.")

    session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_token(raw_token))
    )
    if session is None or session.revoked_at is not None:
        raise InvalidSessionError("Invalid session.")

    now = utcnow()
    if session.expires_at <= now:
        raise InvalidSessionError("Expired session.")

    user = session.user
    if user is None or not user.is_active:
        if session.revoked_at is None:
            session.revoked_at = now
            db.add(session)
            db.commit()
        raise InvalidSessionError("Inactive account.")

    # Avoid a write on every single authenticated request while still keeping
    # ``last_seen_at`` useful for operational visibility.
    if session.last_seen_at is None or now - session.last_seen_at >= timedelta(
        minutes=5
    ):
        session.last_seen_at = now
        db.add(session)
        db.commit()

    return session


def revoke_session(db: Session, session: AuthSession) -> None:
    """Invalidate a session immediately."""
    if session.revoked_at is None:
        session.revoked_at = utcnow()
        db.add(session)
        db.commit()


def validate_csrf(
    session: AuthSession, csrf_cookie: str | None, csrf_header: str | None
) -> bool:
    """Validate the double-submit CSRF token against the bound session hash."""
    if not csrf_cookie or not csrf_header:
        return False
    if not constant_time_compare(csrf_header, csrf_cookie):
        return False
    return constant_time_compare(hash_token(csrf_header), session.csrf_token_hash)
