from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_csrf, require_roles
from app.core.rate_limit import (
    INCIDENTS_CREATE_POLICY,
    RATE_LIMIT_429_RESPONSE,
    rate_limit,
)
from app.database import get_db
from app.models.enums import IncidentStatus, UserRole
from app.models.user import User
from app.schemas.incident import IncidentCreate, IncidentRead, IncidentUpdate
from app.services import incidents as incident_service

router = APIRouter()

staff_roles = require_roles(UserRole.dispatcher, UserRole.admin)


@router.post(
    "",
    response_model=IncidentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit(INCIDENTS_CREATE_POLICY))],
    responses=RATE_LIMIT_429_RESPONSE,
)
def create_incident(
    payload: IncidentCreate, db: Session = Depends(get_db)
) -> IncidentRead:
    """Public citizen incident submission."""
    return incident_service.create_incident(db, payload)


@router.get(
    "",
    response_model=list[IncidentRead],
    dependencies=[Depends(staff_roles)],
)
def list_incidents(
    category: str | None = Query(default=None, max_length=100),
    status_filter: IncidentStatus | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None, max_length=30),
    priority: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[IncidentRead]:
    return incident_service.list_incidents(
        db,
        category=category,
        status=status_filter.value if status_filter else None,
        severity=severity,
        priority=priority,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{incident_id}",
    response_model=IncidentRead,
    dependencies=[Depends(staff_roles)],
)
def get_incident(incident_id: int, db: Session = Depends(get_db)) -> IncidentRead:
    incident = incident_service.get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return incident


@router.patch(
    "/{incident_id}",
    response_model=IncidentRead,
    dependencies=[Depends(require_csrf)],
)
def update_incident(
    incident_id: int,
    payload: IncidentUpdate,
    current_user: User = Depends(staff_roles),
    db: Session = Depends(get_db),
) -> IncidentRead:
    incident = incident_service.get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return incident_service.update_incident(
        db, incident, payload, actor=current_user
    )
