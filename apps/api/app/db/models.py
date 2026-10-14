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
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"))
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


# ─── Graph Versioning ───────────────────────────────────────────────


class GraphVersion(Base):
    __tablename__ = "graph_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number = Column(String(50), nullable=False)
    content_hash = Column(String(64), nullable=False)
    snapshot = Column(JSONB, default=dict)
    change_description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ─── Schema Drift & Golden Path ───────────────────────────────────────


class SchemaSnapshot(Base):
    """Point-in-time schema snapshot for drift detection."""

    __tablename__ = "schema_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    connector_id = Column(String(100), nullable=False)
    table_name = Column(String(500), nullable=False)
    schema_def = Column(JSONB, nullable=False)
    column_count = Column(Float)
    content_hash = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RemediationPlan(Base):
    """Structured remediation plan for incidents."""

    __tablename__ = "remediation_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), nullable=False)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(String(30), default="draft")
    risk_level = Column(String(20), default="medium")
    requires_approval = Column(Boolean, default=True)
    actions = Column(JSONB, default=list)
    rollback_plan = Column(JSONB, default=list)
    verification_criteria = Column(JSONB, default=list)
    approved_by = Column(String(100))
    approved_at = Column(DateTime(timezone=True))
    executed_at = Column(DateTime(timezone=True))
    verified_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    """Product tier subscription for an organization."""

    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    tier = Column(String(30), default="observe")
    started_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    extra_data = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ReliabilityScoreHistory(Base):
    """Historical reliability score records per organization."""

    __tablename__ = "reliability_score_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    overall_score = Column(Float, default=0.0)
    grade = Column(String(5), default="F")
    dimensions = Column(JSONB, default=dict)
    recommendations = Column(JSONB, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class IncidentMemoryRecord(Base):
    """Persistent incident memory with Failure DNA fingerprints."""

    __tablename__ = "incident_memory_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    incident_id = Column(String(100), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, default="")
    severity = Column(String(20), default="medium")
    category = Column(String(100), default="unknown")
    root_cause = Column(Text, default="")
    resolution = Column(Text, default="")
    affected_services = Column(JSONB, default=list)
    error_signatures = Column(JSONB, default=list)
    failure_dna_hash = Column(String(64), default="")
    failure_dna_fingerprint = Column(String(200), default="")
    resolution_steps = Column(JSONB, default=list)
    environment = Column(String(50), default="production")
    prevention_tip = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChangeEvent(Base):
    """Change events from GitHub, deployments, schema changes."""

    __tablename__ = "change_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    change_id = Column(String(100), nullable=False)
    change_type = Column(String(50), nullable=False)
    description = Column(Text, default="")
    author = Column(String(200), default="")
    affected_resources = Column(JSONB, default=list)
    risk_score = Column(Float, default=0.0)
    extra_data = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RiskPrediction(Base):
    """Preventive risk predictions from change analysis."""

    __tablename__ = "risk_predictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    prediction_id = Column(String(100), nullable=False)
    risk_level = Column(String(20), default="low")
    probability = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    description = Column(Text, default="")
    affected_resources = Column(JSONB, default=list)
    preventive_actions = Column(JSONB, default=list)
    change_id = Column(String(100), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
