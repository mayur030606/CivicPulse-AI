from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReportTrackingRead(BaseModel):
    """Public-safe view of an incident, keyed by its tracking ID."""

    model_config = ConfigDict(from_attributes=True)

    tracking_id: str
    category: str
    status: str | None = None
    severity: str | None = None
    priority: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime | None = None
