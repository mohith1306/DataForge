"""Phase 9: Add schema_snapshots and remediation_plans tables

Revision ID: 002
Revises: 001
Create Date: 2026-09-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schema Snapshots — point-in-time schema snapshots for drift detection
    op.create_table(
        "schema_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("connector_id", sa.String(100), nullable=False),
        sa.Column("table_name", sa.String(500), nullable=False),
        sa.Column("schema_def", postgresql.JSONB(), nullable=False),
        sa.Column("column_count", sa.Float()),
        sa.Column("content_hash", sa.String(64)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_schema_snapshots_org_connector_table",
        "schema_snapshots",
        ["org_id", "connector_id", "table_name"],
    )

    # Remediation Plans — structured repair plans for incidents
    op.create_table(
        "remediation_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(30), server_default="draft"),
        sa.Column("risk_level", sa.String(20), server_default="medium"),
        sa.Column("requires_approval", sa.Boolean, server_default="true"),
        sa.Column("actions", postgresql.JSONB(), server_default="[]"),
        sa.Column("rollback_plan", postgresql.JSONB(), server_default="[]"),
        sa.Column("verification_criteria", postgresql.JSONB(), server_default="[]"),
        sa.Column("approved_by", sa.String(100)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_remediation_plans_incident",
        "remediation_plans",
        ["incident_id"],
    )


def downgrade() -> None:
    op.drop_table("remediation_plans")
    op.drop_table("schema_snapshots")
