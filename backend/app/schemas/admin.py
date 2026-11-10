from pydantic import BaseModel

from app.schemas.reports import GroupCount


class ServiceStatus(BaseModel):
    name: str
    configured: bool
    implemented: bool
    note: str


class AdminOverview(BaseModel):
    incidents_total: int
    citizen_reports_total: int
    incident_images_total: int
    status_history_total: int
    departments_total: int
    incidents_by_status: list[GroupCount]
    services: list[ServiceStatus]
