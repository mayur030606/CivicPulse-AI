"""Pydantic schemas for the existing ``incidents`` table."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import IncidentStatus

ALLOWED_INCIDENT_STATUSES = frozenset(status.value for status in IncidentStatus)


class IncidentBase(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=10000)
    severity: str | None = Field(default=None, max_length=30)
    priority: str | None = Field(default=None, max_length=30)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class IncidentCreate(IncidentBase):
    # Reject unexpected keys instead of silently dropping them. This also
    # prevents clients from supplying tracking_id; the server always generates
    # the public identifier.
    model_config = ConfigDict(extra="forbid")

    # Public reporting may only create the initial workflow state.
    status: Literal["Submitted"] = "Submitted"


class IncidentUpdate(BaseModel):
    # PATCH accepts only the documented mutable fields.
    model_config = ConfigDict(extra="forbid")

    category: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=10000)
    severity: str | None = Field(default=None, max_length=30)
    priority: str | None = Field(default=None, max_length=30)
    status: str | None = Field(default=None, max_length=30)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in ALLOWED_INCIDENT_STATUSES:
            allowed = ", ".join(sorted(ALLOWED_INCIDENT_STATUSES))
            raise ValueError(f"Status must be one of: {allowed}.")
        return value

    @model_validator(mode="after")
    def reject_explicit_null_status(self) -> "IncidentUpdate":
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("Status cannot be null.")
        return self


class IncidentRead(IncidentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tracking_id: str
    status: str | None = None
    created_at: datetime | None = None
