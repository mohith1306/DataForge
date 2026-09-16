"""Schema Verifier — validates schema after remediation.

Compares the schema before remediation (from incident snapshot)
with the current schema to verify the fix worked.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.sensors.schema_drift import SchemaDriftSensor

logger = logging.getLogger(__name__)


class SchemaVerifier:
    """Verifies that schema remediation was successful."""

    def __init__(self, db: AsyncSession, org_id: Any):
        self.db = db
        self.org_id = org_id
        self.sensor = SchemaDriftSensor(db, org_id)

    async def verify(
        self,
        connector_id: str,
        table_name: str,
        current_schema: list[dict],
        expected_schema: list[dict] | None = None,
        drift_snapshot: dict | None = None,
    ) -> dict:
        """Verify schema after remediation.

        Args:
            connector_id: The connector that owns the table
            table_name: The table that was remediated
            current_schema: The current schema after remediation
            expected_schema: The schema we expect (if provided, compare against this)
            drift_snapshot: The original drift snapshot from the incident

        Returns:
            Verification result with pass/fail and details
        """
        result = {
            "passed": True,
            "checks": [],
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

        if expected_schema:
            check = self._compare_schemas(current_schema, expected_schema, "expected_schema")
            result["checks"].append(check)
            if not check["passed"]:
                result["passed"] = False

        if drift_snapshot:
            check = self._verify_drift_resolved(current_schema, drift_snapshot)
            result["checks"].append(check)
            if not check["passed"]:
                result["passed"] = False

        if not expected_schema and not drift_snapshot:
            prev = await self.sensor.get_last_snapshot(connector_id, table_name)
            if prev:
                check = self._compare_schemas(current_schema, prev, "vs_previous_snapshot")
                result["checks"].append(check)
                if not check["passed"]:
                    result["passed"] = False

        await self.sensor.store_snapshot(connector_id, table_name, current_schema)

        return result

    def _compare_schemas(
        self,
        actual: list[dict],
        expected: list[dict],
        check_name: str,
    ) -> dict:
        """Compare two schemas for equality."""
        actual_cols = {c["name"]: c for c in actual}
        expected_cols = {c["name"]: c for c in expected}

        missing = set(expected_cols.keys()) - set(actual_cols.keys())
        extra = set(actual_cols.keys()) - set(expected_cols.keys())

        type_mismatches = []
        for name in set(expected_cols.keys()) & set(actual_cols.keys()):
            exp_type = expected_cols[name].get("type", "").lower()
            act_type = actual_cols[name].get("type", "").lower()
            if exp_type != act_type:
                type_mismatches.append({
                    "column": name,
                    "expected": exp_type,
                    "actual": act_type,
                })

        passed = not missing and not extra and not type_mismatches

        return {
            "check": check_name,
            "passed": passed,
            "missing_columns": sorted(missing),
            "extra_columns": sorted(extra),
            "type_mismatches": type_mismatches,
            "actual_column_count": len(actual),
            "expected_column_count": len(expected),
        }

    def _verify_drift_resolved(
        self,
        current_schema: list[dict],
        drift_snapshot: dict,
    ) -> dict:
        """Verify that the detected drift has been resolved."""
        curr_cols = {c["name"]: c for c in current_schema}

        issues = []

        for removed in drift_snapshot.get("removed_columns", []):
            col_name = removed.get("name", "")
            if col_name not in curr_cols:
                issues.append(f"Column '{col_name}' is still missing")

        for added in drift_snapshot.get("added_columns", []):
            col_name = added.get("name", "")
            if col_name not in curr_cols:
                issues.append(f"Added column '{col_name}' not found in current schema")

        for tc in drift_snapshot.get("type_changes", []):
            col_name = tc.get("column", "")
            expected_type = tc.get("previous_type", "")
            if col_name in curr_cols:
                actual_type = curr_cols[col_name].get("type", "").lower()
                if actual_type != expected_type:
                    issues.append(
                        f"Column '{col_name}' type is {actual_type}, expected {expected_type}"
                    )

        return {
            "check": "drift_resolved",
            "passed": len(issues) == 0,
            "issues": issues,
        }
