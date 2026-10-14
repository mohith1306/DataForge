"""Phase 14: Add commercial MVP tables

Revision ID: 003
Revises: 002
Create Date: 2026-10-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Subscriptions — product tier per org
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("tier", sa.String(30), nullable=False, server_default="observe"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("metadata", postgresql.JSONB, nullable=True, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_subscriptions_org_id", "subscriptions", ["org_id"])

    # Reliability score history
    op.create_table(
        "reliability_score_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("overall_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("grade", sa.String(5), nullable=False, server_default="F"),
        sa.Column("dimensions", postgresql.JSONB, nullable=True, server_default="{}"),
        sa.Column("recommendations", postgresql.JSONB, nullable=True, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_reliability_score_history_org_id", "reliability_score_history", ["org_id"])

    # Incident memory records — Failure DNA
    op.create_table(
        "incident_memory_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("incident_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True, server_default=""),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("category", sa.String(100), nullable=False, server_default="unknown"),
        sa.Column("root_cause", sa.Text, nullable=True, server_default=""),
        sa.Column("resolution", sa.Text, nullable=True, server_default=""),
        sa.Column("affected_services", postgresql.JSONB, nullable=True, server_default="[]"),
        sa.Column("error_signatures", postgresql.JSONB, nullable=True, server_default="[]"),
        sa.Column("failure_dna_hash", sa.String(64), nullable=True, server_default=""),
        sa.Column("failure_dna_fingerprint", sa.String(200), nullable=True, server_default=""),
        sa.Column("resolution_steps", postgresql.JSONB, nullable=True, server_default="[]"),
        sa.Column("environment", sa.String(50), nullable=False, server_default="production"),
        sa.Column("prevention_tip", sa.Text, nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_incident_memory_records_org_id", "incident_memory_records", ["org_id"])
    op.create_index("ix_incident_memory_records_category", "incident_memory_records", ["category"])

    # Change events
    op.create_table(
        "change_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("change_id", sa.String(100), nullable=False),
        sa.Column("change_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True, server_default=""),
        sa.Column("author", sa.String(200), nullable=True, server_default=""),
        sa.Column("affected_resources", postgresql.JSONB, nullable=True, server_default="[]"),
        sa.Column("risk_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB, nullable=True, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_change_events_org_id", "change_events", ["org_id"])

    # Risk predictions
    op.create_table(
        "risk_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prediction_id", sa.String(100), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
        sa.Column("probability", sa.Float, nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("description", sa.Text, nullable=True, server_default=""),
        sa.Column("affected_resources", postgresql.JSONB, nullable=True, server_default="[]"),
        sa.Column("preventive_actions", postgresql.JSONB, nullable=True, server_default="[]"),
        sa.Column("change_id", sa.String(100), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_risk_predictions_org_id", "risk_predictions", ["org_id"])


def downgrade() -> None:
    op.drop_table("risk_predictions")
    op.drop_table("change_events")
    op.drop_table("incident_memory_records")
    op.drop_table("reliability_score_history")
    op.drop_table("subscriptions")
