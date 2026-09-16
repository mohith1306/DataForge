"""Phase 9 Tests — Golden Path: Schema Drift & Pipeline Failure."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from apps.api.app.sensors.schema_drift import SchemaDriftSensor, SchemaDrift
from apps.api.app.services.github_correlation import GitHubCorrelator
from apps.api.app.services.schema_verifier import SchemaVerifier


# ─── Schema Drift Sensor Tests ────────────────────────────────────────


class TestSchemaDriftSensor:
    def test_compare_schemas_added_columns(self):
        sensor = SchemaDriftSensor.__new__(SchemaDriftSensor)
        previous = [
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "varchar"},
        ]
        current = [
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "varchar"},
            {"name": "email", "type": "varchar"},
        ]
        drift = sensor.compare_schemas(previous, current, "users", "conn1")

        assert drift.has_changes
        assert len(drift.added_columns) == 1
        assert drift.added_columns[0]["name"] == "email"
        assert len(drift.removed_columns) == 0
        assert len(drift.type_changes) == 0

    def test_compare_schemas_removed_columns(self):
        sensor = SchemaDriftSensor.__new__(SchemaDriftSensor)
        previous = [
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "varchar"},
            {"name": "age", "type": "integer"},
        ]
        current = [
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "varchar"},
        ]
        drift = sensor.compare_schemas(previous, current, "users", "conn1")

        assert drift.has_changes
        assert len(drift.removed_columns) == 1
        assert drift.removed_columns[0]["name"] == "age"
        assert len(drift.added_columns) == 0

    def test_compare_schemas_type_changes(self):
        sensor = SchemaDriftSensor.__new__(SchemaDriftSensor)
        previous = [
            {"name": "id", "type": "integer"},
            {"name": "age", "type": "integer"},
        ]
        current = [
            {"name": "id", "type": "integer"},
            {"name": "age", "type": "varchar"},
        ]
        drift = sensor.compare_schemas(previous, current, "users", "conn1")

        assert drift.has_changes
        assert len(drift.type_changes) == 1
        assert drift.type_changes[0]["column"] == "age"
        assert drift.type_changes[0]["previous_type"] == "integer"
        assert drift.type_changes[0]["current_type"] == "varchar"

    def test_compare_schemas_no_changes(self):
        sensor = SchemaDriftSensor.__new__(SchemaDriftSensor)
        schema = [
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "varchar"},
        ]
        drift = sensor.compare_schemas(schema, schema, "users", "conn1")

        assert not drift.has_changes
        assert len(drift.added_columns) == 0
        assert len(drift.removed_columns) == 0
        assert len(drift.type_changes) == 0

    def test_compare_schemas_complex_drift(self):
        sensor = SchemaDriftSensor.__new__(SchemaDriftSensor)
        previous = [
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "varchar"},
            {"name": "old_col", "type": "text"},
        ]
        current = [
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "text"},
            {"name": "new_col", "type": "varchar"},
        ]
        drift = sensor.compare_schemas(previous, current, "users", "conn1")

        assert drift.has_changes
        assert len(drift.added_columns) == 1
        assert drift.added_columns[0]["name"] == "new_col"
        assert len(drift.removed_columns) == 1
        assert drift.removed_columns[0]["name"] == "old_col"
        assert len(drift.type_changes) == 1
        assert drift.type_changes[0]["column"] == "name"

    def test_drift_to_dict(self):
        drift = SchemaDrift(
            table_name="users",
            connector_id="conn1",
            added_columns=[{"name": "email", "type": "varchar"}],
            removed_columns=[],
            type_changes=[],
            previous_schema=[],
            current_schema=[],
            detected_at=datetime.now(timezone.utc),
        )
        d = drift.to_dict()
        assert d["table_name"] == "users"
        assert len(d["added_columns"]) == 1
        assert "detected_at" in d

    def test_compute_hash_deterministic(self):
        sensor = SchemaDriftSensor.__new__(SchemaDriftSensor)
        cols = [{"name": "id", "type": "integer"}, {"name": "name", "type": "varchar"}]
        h1 = sensor._compute_hash(cols)
        h2 = sensor._compute_hash(cols)
        assert h1 == h2
        assert len(h1) == 16

    def test_compute_hash_different_schemas(self):
        sensor = SchemaDriftSensor.__new__(SchemaDriftSensor)
        cols1 = [{"name": "id", "type": "integer"}]
        cols2 = [{"name": "id", "type": "varchar"}]
        assert sensor._compute_hash(cols1) != sensor._compute_hash(cols2)


# ─── GitHub Correlation Tests ─────────────────────────────────────────


class TestGitHubCorrelator:
    def test_is_schema_related_commit_message(self):
        correlator = GitHubCorrelator()
        assert correlator._is_schema_related("add migration for users table", [])
        assert correlator._is_schema_related("alter column type", [])
        assert correlator._is_schema_related("rename region column", [])
        assert correlator._is_schema_related("update readme", []) is False

    def test_is_schema_related_file_paths(self):
        correlator = GitHubCorrelator()
        files = [{"filename": "alembic/versions/003_add_column.sql", "patch": ""}]
        assert correlator._is_schema_related("update something", files)

    def test_is_schema_related_patch_content(self):
        correlator = GitHubCorrelator()
        files = [{"filename": "script.py", "patch": "ALTER TABLE users ADD COLUMN email varchar"}]
        assert correlator._is_schema_related("update something", files)

    def test_score_relevance_table_in_message(self):
        correlator = GitHubCorrelator()
        commit = {"message": "add column to users table"}
        files = []
        score = correlator._score_relevance(commit, files, "users", None)
        assert score >= 5.0

    def test_score_relevance_no_match(self):
        correlator = GitHubCorrelator()
        commit = {"message": "update readme"}
        files = [{"filename": "README.md", "patch": ""}]
        score = correlator._score_relevance(commit, files, "users", None)
        assert score == 0.0

    def test_explain_relevance(self):
        correlator = GitHubCorrelator()
        commit = {"message": "migration for users"}
        files = [{"filename": "alembic/versions/003.py", "patch": ""}]
        reason = correlator._explain_relevance(commit, files, "users")
        assert "users" in reason.lower() or "migration" in reason.lower()


# ─── Schema Verifier Tests ────────────────────────────────────────────


class TestSchemaVerifier:
    def test_compare_schemas_match(self):
        verifier = SchemaVerifier.__new__(SchemaVerifier)
        actual = [{"name": "id", "type": "integer"}, {"name": "name", "type": "varchar"}]
        expected = [{"name": "id", "type": "integer"}, {"name": "name", "type": "varchar"}]
        result = verifier._compare_schemas(actual, expected, "test")
        assert result["passed"]
        assert len(result["missing_columns"]) == 0
        assert len(result["extra_columns"]) == 0

    def test_compare_schemas_missing_column(self):
        verifier = SchemaVerifier.__new__(SchemaVerifier)
        actual = [{"name": "id", "type": "integer"}]
        expected = [{"name": "id", "type": "integer"}, {"name": "email", "type": "varchar"}]
        result = verifier._compare_schemas(actual, expected, "test")
        assert not result["passed"]
        assert "email" in result["missing_columns"]

    def test_compare_schemas_extra_column(self):
        verifier = SchemaVerifier.__new__(SchemaVerifier)
        actual = [
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "varchar"},
            {"name": "extra", "type": "text"},
        ]
        expected = [{"name": "id", "type": "integer"}, {"name": "name", "type": "varchar"}]
        result = verifier._compare_schemas(actual, expected, "test")
        assert not result["passed"]
        assert "extra" in result["extra_columns"]

    def test_compare_schemas_type_mismatch(self):
        verifier = SchemaVerifier.__new__(SchemaVerifier)
        actual = [{"name": "id", "type": "varchar"}]
        expected = [{"name": "id", "type": "integer"}]
        result = verifier._compare_schemas(actual, expected, "test")
        assert not result["passed"]
        assert len(result["type_mismatches"]) == 1

    def test_verify_drift_resolved(self):
        verifier = SchemaVerifier.__new__(SchemaVerifier)
        # Column was removed in drift but is now present — drift is resolved
        current = [{"name": "id", "type": "integer"}, {"name": "email", "type": "varchar"}]
        drift_snapshot = {
            "removed_columns": [{"name": "email"}],
            "added_columns": [],
            "type_changes": [],
        }
        result = verifier._verify_drift_resolved(current, drift_snapshot)
        assert result["passed"]
        assert len(result["issues"]) == 0

    def test_verify_drift_not_resolved(self):
        verifier = SchemaVerifier.__new__(SchemaVerifier)
        # Column was removed in drift and is STILL missing — drift not resolved
        current = [{"name": "id", "type": "integer"}]
        drift_snapshot = {
            "removed_columns": [{"name": "email"}],
            "added_columns": [],
            "type_changes": [],
        }
        result = verifier._verify_drift_resolved(current, drift_snapshot)
        assert not result["passed"]
        assert len(result["issues"]) == 1

    def test_verify_drift_still_present(self):
        verifier = SchemaVerifier.__new__(SchemaVerifier)
        current = [{"name": "id", "type": "integer"}]
        drift_snapshot = {
            "removed_columns": [],
            "added_columns": [{"name": "email", "type": "varchar"}],
            "type_changes": [],
        }
        result = verifier._verify_drift_resolved(current, drift_snapshot)
        assert not result["passed"]
        assert len(result["issues"]) == 1


# ─── Model Tests ──────────────────────────────────────────────────────


class TestPhase9Models:
    def test_schema_snapshot_model(self):
        from apps.api.app.db.models import SchemaSnapshot

        assert SchemaSnapshot.__tablename__ == "schema_snapshots"
        cols = {c.name for c in SchemaSnapshot.__table__.columns}
        assert "org_id" in cols
        assert "connector_id" in cols
        assert "table_name" in cols
        assert "schema_def" in cols
        assert "content_hash" in cols

    def test_remediation_plan_model(self):
        from apps.api.app.db.models import RemediationPlan

        assert RemediationPlan.__tablename__ == "remediation_plans"
        cols = {c.name for c in RemediationPlan.__table__.columns}
        assert "incident_id" in cols
        assert "status" in cols
        assert "risk_level" in cols
        assert "actions" in cols
        assert "rollback_plan" in cols
        assert "requires_approval" in cols


# ─── Migration Tests ──────────────────────────────────────────────────


class TestPhase9Migration:
    def test_migration_file_exists(self):
        import os

        migration_path = "alembic/versions/002_phase9_schema_drift_tables.py"
        assert os.path.exists(migration_path)

    def test_migration_has_required_tables(self):
        with open("alembic/versions/002_phase9_schema_drift_tables.py") as f:
            content = f.read()
        assert "schema_snapshots" in content
        assert "remediation_plans" in content
        assert "schema_def" in content
        assert "actions" in content
