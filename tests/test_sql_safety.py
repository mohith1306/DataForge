"""Tests for SQL safety and validation."""

import pytest

from mcp.database.tools.sql_safety import (
    SQLSafetyError,
    enforce_row_limit,
    validate_query,
)


class TestValidateQuery:
    """Test SQL query validation."""

    def test_valid_select(self):
        result = validate_query("SELECT * FROM orders")
        assert result == "SELECT * FROM orders"

    def test_lowercase_select(self):
        result = validate_query("select count(*) from orders")
        assert result.upper().startswith("SELECT")

    def test_empty_query(self):
        with pytest.raises(SQLSafetyError, match="Empty query"):
            validate_query("")

    def test_whitespace_only(self):
        with pytest.raises(SQLSafetyError, match="Empty query"):
            validate_query("   ")

    def test_insert_blocked(self):
        with pytest.raises(SQLSafetyError, match="Blocked keyword"):
            validate_query("INSERT INTO orders VALUES (1)")

    def test_delete_blocked(self):
        with pytest.raises(SQLSafetyError, match="Blocked keyword"):
            validate_query("DELETE FROM orders WHERE id=1")

    def test_update_blocked(self):
        with pytest.raises(SQLSafetyError, match="Blocked keyword"):
            validate_query("UPDATE orders SET status='done'")

    def test_drop_blocked(self):
        with pytest.raises(SQLSafetyError, match="Blocked keyword"):
            validate_query("DROP TABLE orders")

    def test_semicolon_blocked(self):
        with pytest.raises(SQLSafetyError):
            validate_query("SELECT * FROM orders; DROP TABLE orders")

    def test_strips_trailing_semicolon(self):
        result = validate_query("SELECT * FROM orders;")
        assert result == "SELECT * FROM orders"

    def test_max_length_exceeded(self):
        long_query = "SELECT * FROM orders WHERE " + "x=1 AND " * 1000
        with pytest.raises(SQLSafetyError, match="exceeds max length"):
            validate_query(long_query)


class TestEnforceRowLimit:
    """Test row limit enforcement."""

    def test_adds_limit(self):
        sql = "SELECT * FROM orders"
        result = enforce_row_limit(sql, 100)
        assert "LIMIT 100" in result

    def test_preserves_existing_limit(self):
        sql = "SELECT * FROM orders LIMIT 50"
        result = enforce_row_limit(sql, 100)
        assert "LIMIT 50" in result

    def test_reduces_large_limit(self):
        sql = "SELECT * FROM orders LIMIT 10000"
        result = enforce_row_limit(sql, 100)
        assert "LIMIT 100" in result
