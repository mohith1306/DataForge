"""Database MCP tools — real ClickHouse implementations."""

import re

from mcp.database.tools.client import clickhouse_client
from mcp.database.tools.sql_safety import SQLSafetyError, add_row_limit, validate_query

# Allow only alphanumeric + underscore for identifiers
IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_identifier(name: str, kind: str = "identifier") -> str:
    """Validate that a name is a safe SQL identifier."""
    if not name or not IDENTIFIER_PATTERN.match(name):
        raise SQLSafetyError(f"Invalid {kind}: {name!r}")
    return name


async def list_tables(database: str = "dataforge") -> dict:
    """List all tables in the specified database."""
    try:
        _validate_identifier(database, "database")
        tables = await clickhouse_client.list_tables(database)
        return {"tables": tables, "count": len(tables)}
    except SQLSafetyError as e:
        return {"error": str(e), "tables": []}
    except Exception as e:
        return {"error": str(e), "tables": []}


async def describe_table(table: str, database: str = "dataforge") -> dict:
    """Get column definitions for a table."""
    try:
        _validate_identifier(table, "table")
        _validate_identifier(database, "database")
        columns = await clickhouse_client.describe_table(table, database)
        return {"table": table, "columns": columns, "count": len(columns)}
    except SQLSafetyError as e:
        return {"error": str(e), "table": table, "columns": []}
    except Exception as e:
        return {"error": str(e), "table": table, "columns": []}


async def execute_select(query: str) -> dict:
    """Execute a read-only SELECT query with safety validation."""
    try:
        safe_query = validate_query(query)
        safe_query = add_row_limit(safe_query)
        rows = await clickhouse_client.execute(safe_query)
        return {
            "query": safe_query,
            "row_count": len(rows),
            "rows": rows[:100],
        }
    except SQLSafetyError as e:
        return {"error": f"Safety violation: {e}", "query": query, "rows": []}
    except Exception as e:
        return {"error": str(e), "query": query, "rows": []}


async def profile_column(table: str, column: str) -> dict:
    """Profile a column: null rate, distinct count, min, max, avg."""
    try:
        _validate_identifier(table, "table")
        _validate_identifier(column, "column")

        query = (
            f"SELECT "
            f"count() as total, "
            f"countIf(isNull({column})) as null_count, "
            f"uniq({column}) as distinct_count, "
            f"min({column}) as min_val, "
            f"max({column}) as max_val "
            f"FROM dataforge.{table}"
        )
        rows = await clickhouse_client.execute(query)
        if rows:
            r = rows[0]
            total = r.get("total", 0)
            null_count = r.get("null_count", 0)
            return {
                "table": table,
                "column": column,
                "total_rows": total,
                "null_count": null_count,
                "null_rate": round(null_count / max(total, 1), 4),
                "distinct_count": r.get("distinct_count", 0),
                "min_val": str(r.get("min_val", "")),
                "max_val": str(r.get("max_val", "")),
            }
        return {"error": "No results", "table": table, "column": column}
    except SQLSafetyError as e:
        return {"error": str(e), "table": table, "column": column}
    except Exception as e:
        return {"error": str(e), "table": table, "column": column}


async def get_recent_records(table: str, limit: int = 10) -> dict:
    """Get recent records from a table."""
    try:
        _validate_identifier(table, "table")
        limit = min(max(1, limit), 10000)

        query = f"SELECT * FROM dataforge.{table} ORDER BY 1 DESC LIMIT {limit}"
        rows = await clickhouse_client.execute(query)
        return {"table": table, "rows": rows, "count": len(rows)}
    except SQLSafetyError as e:
        return {"error": str(e), "table": table, "rows": []}
    except Exception as e:
        return {"error": str(e), "table": table, "rows": []}
