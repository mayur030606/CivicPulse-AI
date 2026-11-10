"""Business logic for incidents, backed by the existing ``incidents`` table."""

import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.incident import Incident
from app.models.status_history import StatusHistory
from app.models.user import User
from app.schemas.incident import IncidentCreate, IncidentUpdate


def generate_tracking_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    suffix = secrets.token_hex(3).upper()
    return f"CP-{stamp}-{suffix}"


def create_incident(db: Session, payload: IncidentCreate) -> Incident:
    data = payload.model_dump()
    # Always generate the public identifier server-side. IncidentCreate rejects
    # client-supplied tracking_id, so this value cannot be overridden.
    data["tracking_id"] = generate_tracking_id()

    incident = Incident(**data)
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def list_incidents(
    db: Session,
    *,
    category: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    priority: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Incident]:
    query = select(Incident).order_by(Incident.created_at.desc())

    if category:
        query = query.where(Incident.category == category)
    if status:
        query = query.where(Incident.status == status)
    if severity:
        query = query.where(Incident.severity == severity)
    if priority:
        query = query.where(Incident.priority == priority)

    query = query.limit(limit).offset(offset)
    return list(db.scalars(query).all())


def get_incident(db: Session, incident_id: int) -> Incident | None:
    return db.get(Incident, incident_id)


def get_incident_by_tracking_id(db: Session, tracking_id: str) -> Incident | None:
    return db.scalar(select(Incident).where(Incident.tracking_id == tracking_id))


def update_incident(
    db: Session,
    incident: Incident,
    payload: IncidentUpdate,
    *,
    actor: User | None = None,
) -> Incident:
    changes = payload.model_dump(exclude_unset=True)
    old_status = incident.status

    for field, value in changes.items():
        setattr(incident, field, value)

    new_status = changes.get("status")
    if new_status is not None and new_status != old_status:
        # Audit trail: one row per real status transition. The actor is
        # nullable because pre-existing history rows have no recorded user.
        db.add(
            StatusHistory(
                incident_id=incident.id,
                old_status=old_status,
                new_status=new_status,
                changed_by_user_id=actor.id if actor else None,
                notes=(
                    "Status updated via authenticated API."
                    if actor
                    else "Status updated via API."
                ),
            )
        )

    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident
