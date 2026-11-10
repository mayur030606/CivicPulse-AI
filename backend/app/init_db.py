"""Create only missing tables. Never drops or alters existing tables.

Usage (from ``backend/``):
    python -m app.init_db

The live database already has departments, incidents, citizen_reports,
incident_images and status_history, so this is normally a no-op. It exists for
fresh development databases only. Authentication tables (`users`,
`auth_sessions`) are managed by Alembic instead; run
`python -m alembic upgrade head`.
"""

from app.database import Base, engine
from app.models import (  # noqa: F401  (register models on Base.metadata)
    CitizenReport,
    Department,
    Incident,
    IncidentImage,
    StatusHistory,
)

EXPECTED_TABLES = (
    "departments",
    "incidents",
    "citizen_reports",
    "incident_images",
    "status_history",
)


def init_db() -> None:
    tables = [Base.metadata.tables[name] for name in EXPECTED_TABLES]
    Base.metadata.create_all(bind=engine, tables=tables, checkfirst=True)


if __name__ == "__main__":
    init_db()
    print("Missing tables created (existing tables left unchanged).")
