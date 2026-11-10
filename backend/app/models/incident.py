"""SQLAlchemy model for the existing ``incidents`` table.

The table uses plain VARCHAR status/severity/priority columns, so the model
does not impose database enums. Column types and nullability mirror the live
MySQL schema.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tracking_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(30), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str | None] = mapped_column(
        String(30), nullable=True, server_default=text("'Submitted'")
    )
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, server_default=func.now()
    )

    citizen_reports = relationship("CitizenReport", back_populates="incident")
    images = relationship("IncidentImage", back_populates="incident")
    status_history = relationship(
        "StatusHistory",
        back_populates="incident",
        order_by="StatusHistory.changed_at",
    )
