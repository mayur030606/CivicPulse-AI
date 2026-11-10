"""SQLAlchemy model for the existing ``incident_images`` table."""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class IncidentImage(Base):
    __tablename__ = "incident_images"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id"), nullable=True, index=True
    )
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detection_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    incident = relationship("Incident", back_populates="images")
