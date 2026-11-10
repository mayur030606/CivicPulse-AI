from pydantic import BaseModel


class Message(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class DatabaseHealthResponse(BaseModel):
    database: str


class DatabaseCheckResponse(BaseModel):
    status: str
    database: str
