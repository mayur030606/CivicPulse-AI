"""Models registered for the existing CivicPulse database tables.

The legacy ``Complaint`` model and ``/api/v1/complaints`` routes were removed
in Phase 3C-2A because the live database has no ``complaints`` table. Citizen
reporting now uses the ``incidents`` workflow exclusively.
"""

from app.models.auth_session import AuthSession
from app.models.citizen_report import CitizenReport
from app.models.department import Department
from app.models.incident import Incident
from app.models.incident_image import IncidentImage
from app.models.status_history import StatusHistory
from app.models.user import User

__all__ = [
    "AuthSession",
    "CitizenReport",
    "Department",
    "Incident",
    "IncidentImage",
    "StatusHistory",
    "User",
]
