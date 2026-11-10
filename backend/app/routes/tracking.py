"""Public incident tracking by tracking ID.

Tracking IDs are generated when an incident is created (for example
``CP-20261105-A1B2C3``). This router exposes only a public-safe subset of the
record, not the full incident or its citizen reports.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.rate_limit import (
    RATE_LIMIT_429_RESPONSE,
    TRACKING_LOOKUP_POLICY,
    rate_limit,
)
from app.database import get_db
from app.schemas.tracking import ReportTrackingRead
from app.services import incidents as incident_service

router = APIRouter()


@router.get(
    "/{tracking_id}",
    response_model=ReportTrackingRead,
    dependencies=[Depends(rate_limit(TRACKING_LOOKUP_POLICY))],
    responses=RATE_LIMIT_429_RESPONSE,
)
def track_report(
    tracking_id: str = Path(min_length=3, max_length=50),
    db: Session = Depends(get_db),
) -> ReportTrackingRead:
    incident = incident_service.get_incident_by_tracking_id(
        db, tracking_id.strip().upper()
    )
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found. Check the tracking ID.",
        )
    return incident
