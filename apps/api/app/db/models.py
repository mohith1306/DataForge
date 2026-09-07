"""DataForge API — SQLAlchemy models."""
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ─── Enterprise Models ────────────────────────────────────────────────


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    settings = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False)
    environment = Column(String(50), default="production")
    settings = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(200))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"))
    role = Column(String(50), default="member")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    key_hash = Column(String(255), nullable=False)
    key_prefix = Column(String(8), nullable=False)
    scopes = Column(JSONB, default=lambda: ["read", "write"])
    expires_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)


# ─── Reliability Graph Models ─────────────────────────────────────────


class ReliabilityNode(Base):
    __tablename__ = "reliability_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL")
    )
    node_type = Column(String(50), nullable=False)
    name = Column(String(500), nullable=False)
    external_id = Column(String(500))
    extra_data = Column("metadata", JSONB, default=dict)
    owner_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    business_criticality = Column(String(20), default="medium")
    reliability_score = Column(Float, default=100.0)
    last_incident_at = Column(DateTime(timezone=True))
    last_updated = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReliabilityEdge(Base):
    __tablename__ = "reliability_edges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("reliability_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_id = Column(
        UUID(as_uuid=True),
        ForeignKey("reliability_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    edge_type = Column(String(50), nullable=False)
    extra_data = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ─── Incident Models ──────────────────────────────────────────────────


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    severity = Column(String(20), nullable=False, default="medium")
    status = Column(String(30), nullable=False, default="created")
    incident_type = Column(String(50))
    connector_id = Column(String(100))
    trueforge_session_id = Column(String(100))
    approval_reason = Column(Text)
    verification_result = Column(Text)
    # Enterprise columns
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    reliability_graph_snapshot = Column(JSONB)
    failure_dna = Column(String(500))
    business_impact_score = Column(Float)
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
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class IncidentEvidence(Base):
    __tablename__ = "incident_evidence"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), nullable=False)
    source = Column(String(50), nullable=False)
    type = Column(String(50), nullable=False)
    content = Column(JSONB, default=dict)
    confidence = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class IncidentApproval(Base):
    __tablename__ = "incident_approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    reviewer = Column(String(100))
    reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True))
