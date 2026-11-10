"""Pydantic schemas for authentication endpoints.

These schemas never expose password hashes, session tokens or CSRF tokens.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    # Do not enforce the provisioning policy here: a short password must still
    # return the same generic 401 as a wrong password, not a 422.
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_login_at: datetime | None = None


class LoginResponse(BaseModel):
    user: UserRead
