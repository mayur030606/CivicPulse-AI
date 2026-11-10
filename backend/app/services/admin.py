"""Read-only operational overview for municipal staff.

The corresponding routes require an authenticated administrator. They
intentionally return aggregate data only.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.citizen_report import CitizenReport
from app.models.department import Department
from app.models.incident import Incident
from app.models.incident_image import IncidentImage
from app.models.status_history import StatusHistory
from app.schemas.admin import AdminOverview, ServiceStatus
from app.schemas.reports import GroupCount


def _count(db: Session, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def _status_counts(db: Session, model) -> list[GroupCount]:
    rows = db.execute(
        select(model.status, func.count(model.id))
        .group_by(model.status)
        .order_by(func.count(model.id).desc())
    ).all()
    return [
        GroupCount(value=getattr(value, "value", str(value)), count=count)
        for value, count in rows
    ]


def get_admin_overview(db: Session) -> AdminOverview:
    settings = get_settings()
    gnani_configured = bool(
        settings.gnani_api_key
        and (
            settings.gnani_base_url
            or settings.gnani_stt_url
            or settings.gnani_tts_base_url
        )
    )

    return AdminOverview(
        incidents_total=_count(db, Incident),
        citizen_reports_total=_count(db, CitizenReport),
        incident_images_total=_count(db, IncidentImage),
        status_history_total=_count(db, StatusHistory),
        departments_total=_count(db, Department),
        incidents_by_status=_status_counts(db, Incident),
        services=[
            ServiceStatus(
                name="gnani",
                configured=gnani_configured,
                implemented=True,
                note=(
                    "Gnani Prisma v3.0 STT and Timbre TTS are implemented. "
                    "Evon NLU remains a 501 stub."
                ),
            ),
            ServiceStatus(
                name="yolo",
                configured=bool(settings.yolo_model_path),
                implemented=True,
                note=(
                    "Optional local model (generic COCO labels by default). "
                    "Install requirements-ai.txt if the /ai/analyze-image "
                    "route returns 503."
                ),
            ),
        ],
    )
