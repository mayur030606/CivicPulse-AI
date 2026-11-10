import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import get_settings
from app.core.rate_limit import RateLimitBackendError, build_rate_limiter
from app.core.uploads import UploadBodyLimitMiddleware, upload_body_limits
from app.database import engine
from app.routes import api_router
from app.services.errors import ServiceNotConfiguredError, ServiceUnavailableError

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    app.state.rate_limiter = build_rate_limiter(settings)
    app.state.rate_limit_initialized = True
    try:
        yield
    finally:
        limiter = getattr(app.state, "rate_limiter", None)
        if limiter is not None:
            limiter.close()
        engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Multilingual civic complaint and traffic incident intelligence API. "
        "Gnani Prisma speech-to-text and Timbre text-to-speech are available "
        "when GNANI_API_KEY is configured."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    UploadBodyLimitMiddleware,
    limits=upload_body_limits(settings),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ServiceNotConfiguredError)
async def handle_service_not_configured(
    _request: Request, exc: ServiceNotConfiguredError
) -> JSONResponse:
    return JSONResponse(status_code=501, content={"detail": str(exc)})


@app.exception_handler(NotImplementedError)
async def handle_not_implemented(
    _request: Request, exc: NotImplementedError
) -> JSONResponse:
    return JSONResponse(status_code=501, content={"detail": str(exc)})


@app.exception_handler(ServiceUnavailableError)
async def handle_service_unavailable(
    _request: Request, exc: ServiceUnavailableError
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(RateLimitBackendError)
async def handle_rate_limit_backend_error(
    _request: Request, _exc: RateLimitBackendError
) -> JSONResponse:
    # Fail closed without exposing backend names, URLs or client identifiers.
    logger.error("Rate-limit backend unavailable.")
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Rate limiting is temporarily unavailable. "
                "Please try again later."
            )
        },
    )


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(
    _request: Request, _exc: SQLAlchemyError
) -> JSONResponse:
    # Avoid leaking connection strings or credentials in the response.
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Database unavailable. Check DATABASE_URL (or DB_HOST, DB_USER, "
                "DB_PASSWORD and DB_NAME) and that MySQL is running."
            )
        },
    )


@app.exception_handler(IntegrityError)
async def handle_integrity_error(
    _request: Request, _exc: IntegrityError
) -> JSONResponse:
    # Never echo SQL, column values or driver details.
    return JSONResponse(
        status_code=409,
        content={"detail": "Database constraint violation."},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Log the traceback server-side, but never expose it to the client.
    logger.exception(
        "Unhandled error while processing %s %s", request.method, request.url.path
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {
        "message": "Welcome to the CivicPulse AI API",
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "api": settings.api_v1_prefix,
    }


@app.get("/health", tags=["health"])
def root_health() -> dict[str, str]:
    """Unversioned liveness probe used by containers and uptime checks."""
    return {"status": "healthy"}


# The aggregated router includes the voice router, so
# POST /api/v1/voice/transcribe is registered here.
app.include_router(api_router, prefix=settings.api_v1_prefix)
