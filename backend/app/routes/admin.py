"""Administrative read-only endpoints.

All routes in this router require an authenticated administrator. Dispatcher
and viewer sessions receive ``403`` even though they are valid staff accounts.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.enums import UserRole
from app.schemas.admin import AdminOverview
from app.services import admin as admin_service

router = APIRouter()


@router.get(
    "/overview",
    response_model=AdminOverview,
    dependencies=[Depends(require_roles(UserRole.admin))],
)
def admin_overview(db: Session = Depends(get_db)) -> AdminOverview:
    """Return aggregate incident counts and service status."""
    return admin_service.get_admin_overview(db)
