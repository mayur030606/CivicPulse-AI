"""Password hashing, token generation and constant-time comparison helpers.

Passwords use Argon2id. Session and CSRF tokens are 256-bit random values;
only their SHA-256 digests are stored in the database.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, HashingError, InvalidHashError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

# OWASP-recommended Argon2id baseline (19 MiB, t=2) with a slightly higher
# time cost for a public-sector admin application.
_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


class PasswordPolicyError(ValueError):
    """Raised when a password does not meet the minimum policy."""


def utcnow() -> datetime:
    """Return a naive UTC timestamp for MySQL ``DATETIME`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2id."""
    if not isinstance(password, str) or not password:
        raise ValueError("Password is required.")
    try:
        return _PASSWORD_HASHER.hash(password)
    except HashingError as exc:  # pragma: no cover - defensive
        raise ValueError("Password could not be hashed.") from exc


def verify_password(password_hash: str, password: str) -> bool:
    """Return True only for a matching password/hash pair."""
    if not password_hash or not isinstance(password, str):
        return False
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (Argon2Error, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """Return True when the stored hash uses outdated parameters."""
    try:
        return _PASSWORD_HASHER.check_needs_rehash(password_hash)
    except (Argon2Error, InvalidHashError, ValueError):
        return True


def validate_password_strength(password: str) -> None:
    """Enforce the password policy used by account provisioning.

    There is deliberately no default password anywhere in the application.
    """
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters long."
        )
    if password.strip() != password:
        raise PasswordPolicyError("Password must not start or end with whitespace.")


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """A fixed Argon2id hash used to equalise timing for unknown emails."""
    return hash_password("civicpulse-timing-guard-not-a-login-password")


def generate_session_token() -> str:
    """Generate a high-entropy opaque session cookie value."""
    return secrets.token_urlsafe(48)


def generate_csrf_token() -> str:
    """Generate a high-entropy CSRF token bound to one session."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return a stable SHA-256 digest for a high-entropy token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_compare(left: str, right: str) -> bool:
    """Compare two strings without leaking their contents through timing."""
    if not left or not right:
        return False
    return secrets.compare_digest(left, right)
