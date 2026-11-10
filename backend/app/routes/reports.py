"""Report analytics endpoints.

Incident intake lives in ``routes/incidents.py``. This router adds aggregate
views that the dashboard needs without duplicating the CRUD endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.enums import UserRole
from app.schemas.reports import ReportSummary
from app.services import reports as report_service

router = APIRouter()


@router.get(
    "/summary",
    response_model=ReportSummary,
    dependencies=[
        Depends(require_roles(UserRole.dispatcher, UserRole.admin))
    ],
)
def report_summary(db: Session = Depends(get_db)) -> ReportSummary:
    """Return incident totals grouped by status, priority, severity and category."""
    return report_service.get_report_summary(db)
