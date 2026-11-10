"""Aggregation queries for incident/report analytics.

Routes stay thin; the SQL lives here so it can be reused by the dashboard and
admin endpoints.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.incident import Incident
from app.schemas.reports import GroupCount, ReportSummary


def _group_counts(db: Session, column) -> list[GroupCount]:
    rows = db.execute(
        select(column, func.count(Incident.id))
        .group_by(column)
        .order_by(func.count(Incident.id).desc())
    ).all()
    return [
        GroupCount(value=getattr(value, "value", str(value)), count=count)
        for value, count in rows
    ]


def get_report_summary(db: Session) -> ReportSummary:
    total = db.scalar(select(func.count()).select_from(Incident)) or 0
    return ReportSummary(
        total=total,
        by_status=_group_counts(db, Incident.status),
        by_priority=_group_counts(db, Incident.priority),
        by_severity=_group_counts(db, Incident.severity),
        by_category=_group_counts(db, Incident.category),
    )
