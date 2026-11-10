"""Authentication endpoints.

Authentication uses an opaque HttpOnly session cookie plus a non-HttpOnly
CSRF cookie. Unsafe authenticated requests must send the CSRF cookie value in
the configured ``X-CSRF-Token`` header.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import AuthContext, get_current_auth, get_current_user, require_csrf
from app.core.network import resolve_client_ip
from app.core.rate_limit import (
    LOGIN_POLICY,
    RATE_LIMIT_429_RESPONSE,
    rate_limit,
)
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, UserRead
from app.services import auth as auth_service

router = APIRouter()
settings = get_settings()


def _cookie_settings() -> dict[str, object]:
    return {
        "path": "/",
        "secure": settings.effective_cookie_secure,
        "samesite": (settings.cookie_samesite or "lax").lower(),
    }


def _set_auth_cookies(
    response: Response, session_token: str, csrf_token: str
) -> None:
    max_age = settings.session_ttl_minutes * 60
    common = _cookie_settings()

    response.set_cookie(
        key=settings.auth_cookie_name,
        value=session_token,
        max_age=max_age,
        httponly=True,
        **common,
    )
    # Readable by the browser so the SPA can echo it in the CSRF header. It is
    # not an authentication credential on its own.
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        **common,
    )


def _clear_auth_cookies(response: Response) -> None:
    common = _cookie_settings()
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        **common,
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        httponly=False,
        **common,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    dependencies=[Depends(rate_limit(LOGIN_POLICY))],
    responses=RATE_LIMIT_429_RESPONSE,
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Authenticate and issue an HttpOnly session cookie."""
    try:
        user = auth_service.authenticate_user(db, payload.email, payload.password)
    except auth_service.AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_service.GENERIC_AUTH_ERROR,
            headers={"WWW-Authenticate": "Cookie"},
        ) from exc

    _session, session_token, csrf_token = auth_service.create_session(
        db,
        user,
        ip_address=resolve_client_ip(
            request, settings.rate_limit_trusted_proxy_networks
        ),
        user_agent=request.headers.get("user-agent"),
    )
    _set_auth_cookies(response, session_token, csrf_token)
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
def me(
    response: Response,
    user: User = Depends(get_current_user),
) -> UserRead:
    """Return the currently authenticated user."""
    response.headers["Cache-Control"] = "no-store"
    return UserRead.model_validate(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def logout(
    response: Response,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> None:
    """Revoke the current session and clear both auth cookies."""
    auth_service.revoke_session(db, auth.session)
    _clear_auth_cookies(response)
    response.headers["Cache-Control"] = "no-store"
    return None
