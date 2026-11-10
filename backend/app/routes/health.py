"""Health and database-connectivity endpoints.

Connection failures return a generic 503 message. Exception details, hostnames
and credentials are logged server-side only and never sent to the client.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.database import check_connection
from app.schemas.common import (
    DatabaseCheckResponse,
    DatabaseHealthResponse,
    HealthResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get("/db-health", response_model=DatabaseCheckResponse)
def db_health() -> DatabaseCheckResponse:
    """Test the MySQL connection using a lightweight ``SELECT 1``."""
    try:
        check_connection()
    except SQLAlchemyError:
        logger.exception("Database health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed. Check the server logs.",
        ) from None

    return DatabaseCheckResponse(status="healthy", database="connected")


@router.get("/health/db", response_model=DatabaseHealthResponse)
def database_health() -> DatabaseHealthResponse:
    """Backwards-compatible alias of /db-health."""
    try:
        check_connection()
    except SQLAlchemyError:
        logger.exception("Database health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed. Check the server logs.",
        ) from None

    return DatabaseHealthResponse(database="ok")
