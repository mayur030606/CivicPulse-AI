from pydantic import BaseModel


class GroupCount(BaseModel):
    """A single value/count pair used in aggregate responses."""

    value: str
    count: int


class ReportSummary(BaseModel):
    total: int
    by_status: list[GroupCount]
    by_priority: list[GroupCount]
    by_severity: list[GroupCount]
    by_category: list[GroupCount]
