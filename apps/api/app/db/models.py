"""DataForge API — SQLAlchemy models."""
import uuid

from sqlalchemy import Column, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    severity = Column(String(20), nullable=False, default="medium")
    status = Column(String(30), nullable=False, default="created")
    incident_type = Column(String(50))
    trueforge_session_id = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True))


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), nullable=False)
    type = Column(String(50), nullable=False)
    agent = Column(String(50))
    tool = Column(String(100))
    message = Column(Text)
    metadata_ = Column("metadata", Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
