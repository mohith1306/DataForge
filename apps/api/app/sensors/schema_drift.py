"""Schema Drift Sensor — detects column changes in monitored databases.

The sensor:
1. Fetches current schema from a connector
2. Compares against the last stored snapshot
3. Detects: column additions, removals, type changes
4. Creates incidents when drift is found
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import Incident, ReliabilityNode, SchemaSnapshot

logger = logging.getLogger(__name__)


@dataclass
class SchemaDrift:
    """Describes a detected schema drift."""

    table_name: str
    connector_id: str
    added_columns: list[dict[str, Any]]
    removed_columns: list[dict[str, Any]]
    type_changes: list[dict[str, Any]]
    previous_schema: list[dict[str, Any]]
    current_schema: list[dict[str, Any]]
    detected_at: datetime

    @property
    def has_changes(self) -> bool:
        return bool(
            self.added_columns or self.removed_columns or self.type_changes
        )

    def to_dict(self) -> dict:
        return {
            "table_name": self.table_name,
            "connector_id": self.connector_id,
            "added_columns": self.added_columns,
            "removed_columns": self.removed_columns,
            "type_changes": self.type_changes,
            "column_count_before": len(self.previous_schema),
            "column_count_after": len(self.current_schema),
            "detected_at": self.detected_at.isoformat(),
        }


class SchemaDriftSensor:
    """Detects schema drift by comparing current vs stored snapshots."""

    def __init__(self, db: AsyncSession, org_id: Any):
        self.db = db
        self.org_id = org_id

    def _compute_hash(self, columns: list[dict]) -> str:
        """Compute content hash for a schema definition."""
        content = json.dumps(columns, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def get_last_snapshot(
        self, connector_id: str, table_name: str
    ) -> list[dict] | None:
        """Get the most recent schema snapshot for a table."""
        stmt = (
            select(SchemaSnapshot)
            .where(
                SchemaSnapshot.org_id == self.org_id,
                SchemaSnapshot.connector_id == connector_id,
                SchemaSnapshot.table_name == table_name,
            )
            .order_by(SchemaSnapshot.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        snapshot = result.scalar_one_or_none()
        if snapshot:
            return snapshot.schema_def
        return None

    async def store_snapshot(
        self,
        connector_id: str,
        table_name: str,
        columns: list[dict],
    ) -> SchemaSnapshot:
        """Store a new schema snapshot."""
        snapshot = SchemaSnapshot(
            org_id=self.org_id,
            connector_id=connector_id,
            table_name=table_name,
            schema_def=columns,
            column_count=len(columns),
            content_hash=self._compute_hash(columns),
        )
        self.db.add(snapshot)
        await self.db.flush()
        return snapshot

    def compare_schemas(
        self,
        previous: list[dict[str, Any]],
        current: list[dict[str, Any]],
        table_name: str,
        connector_id: str,
    ) -> SchemaDrift:
        """Compare two schema versions and return drift details."""
        prev_cols = {c["name"]: c for c in previous}
        curr_cols = {c["name"]: c for c in current}

        prev_names = set(prev_cols.keys())
        curr_names = set(curr_cols.keys())

        added = [curr_cols[n] for n in sorted(curr_names - prev_names)]
        removed = [prev_cols[n] for n in sorted(prev_names - curr_names)]

        type_changes = []
        for name in sorted(prev_names & curr_names):
            prev_type = prev_cols[name].get("type", "").lower()
            curr_type = curr_cols[name].get("type", "").lower()
            if prev_type != curr_type:
                type_changes.append(
                    {
                        "column": name,
                        "previous_type": prev_type,
                        "current_type": curr_type,
                    }
                )

        return SchemaDrift(
            table_name=table_name,
            connector_id=connector_id,
            added_columns=added,
            removed_columns=removed,
            type_changes=type_changes,
            previous_schema=previous,
            current_schema=current,
            detected_at=datetime.now(timezone.utc),
        )

    async def detect(
        self,
        connector_id: str,
        table_name: str,
        current_schema: list[dict],
    ) -> SchemaDrift | None:
        """Detect drift for a single table. Returns drift if detected, None if unchanged."""
        previous = await self.get_last_snapshot(connector_id, table_name)

        if previous is None:
            await self.store_snapshot(connector_id, table_name, current_schema)
            return None

        drift = self.compare_schemas(previous, current_schema, table_name, connector_id)

        if drift.has_changes:
            return drift

        return None

    async def create_incident_from_drift(
        self,
        drift: SchemaDrift,
        connector_name: str = "",
    ) -> Incident:
        """Create an incident from detected schema drift."""
        severity = "high" if drift.removed_columns or drift.type_changes else "medium"

        description_parts = [f"Schema drift detected in `{drift.table_name}`"]
        if drift.added_columns:
            names = ", ".join(f"`{c['name']}`" for c in drift.added_columns)
            description_parts.append(f"Columns added: {names}")
        if drift.removed_columns:
            names = ", ".join(f"`{c['name']}`" for c in drift.removed_columns)
            description_parts.append(f"Columns removed: {names}")
        if drift.type_changes:
            for tc in drift.type_changes:
                description_parts.append(
                    f"Column `{tc['column']}` type changed: "
                    f"{tc['previous_type']} → {tc['current_type']}"
                )

        incident = Incident(
            title=f"Schema Drift: {drift.table_name}",
            description="\n".join(description_parts),
            severity=severity,
            status="created",
            incident_type="schema_drift",
            connector_id=drift.connector_id,
            reliability_graph_snapshot=drift.to_dict(),
            org_id=self.org_id,
        )
        self.db.add(incident)
        await self.db.flush()

        evidence_content = {
            "drift": drift.to_dict(),
            "connector_name": connector_name,
        }
        from apps.api.app.db.models import IncidentEvidence

        evidence = IncidentEvidence(
            incident_id=incident.id,
            source="schema_drift_sensor",
            type="schema_drift",
            content=evidence_content,
            confidence=1.0,
        )
        self.db.add(evidence)
        await self.db.flush()

        return incident
