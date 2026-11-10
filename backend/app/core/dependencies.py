"""Reusable FastAPI authentication, CSRF and role dependencies.

The auth routes and the protected incident, report and admin routes share these
dependencies so authorization behaviour stays consistent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, Security, status
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import get_db
from app.models.auth_session import AuthSession
from app.models.enums import UserRole
from app.models.user import User
from app.services import auth as auth_service

settings = get_settings()

session_cookie_scheme = APIKeyCookie(
    name=settings.auth_cookie_name,
    scheme_name="SessionCookie",
    description=(
        "Opaque HttpOnly session cookie issued by POST /api/v1/auth/login. "
        "The server stores only a SHA-256 hash of this value."
    ),
    auto_error=False,
)


@dataclass(frozen=True)
class AuthContext:
    """The authenticated user and the session that proved their identity."""

    user: User
    session: AuthSession


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Cookie"},
    )


def get_current_auth(
    request: Request,
    db: Session = Depends(get_db),
    cookie_token: str | None = Security(session_cookie_scheme),
) -> AuthContext:
    """Resolve the current session from the HttpOnly cookie."""
    raw_token = cookie_token or request.cookies.get(settings.auth_cookie_name)
    if not raw_token:
        raise _unauthorized()

    try:
        session = auth_service.get_active_session(db, raw_token)
    except auth_service.InvalidSessionError as exc:
        raise _unauthorized() from exc

    return AuthContext(user=session.user, session=session)


def get_current_user(auth: AuthContext = Depends(get_current_auth)) -> User:
    """Return the authenticated user, or raise 401."""
    return auth.user


def require_roles(*allowed_roles: UserRole | str) -> Callable[..., User]:
    """Build a dependency that enforces at least one of the given roles."""
    allowed = {
        role.value if isinstance(role, UserRole) else str(role)
        for role in allowed_roles
    }

    def role_dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return user

    return role_dependency


def require_csrf(
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    csrf_header: str | None = Header(
        default=None, alias=settings.csrf_header_name
    ),
) -> None:
    """Enforce the session-bound double-submit CSRF token.

    The browser sends the non-HttpOnly CSRF cookie value in the
    ``X-CSRF-Token`` header. Both values must match the hash bound to the
    current server-side session.
    """
    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
    if not auth_service.validate_csrf(auth.session, csrf_cookie, csrf_header):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed.",
        )
