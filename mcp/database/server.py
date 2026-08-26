"""Database MCP server — tools for investigating ClickHouse data.

Tool risk levels:
- list_tables: LOW
- describe_table: LOW
- execute_select: LOW (read-only, validated)
- profile_column: LOW
- get_recent_records: LOW
"""

from mcp.database.tools.schema import (
    describe_table,
    execute_select,
    get_recent_records,
    list_tables,
    profile_column,
)

MCP_TOOLS = [
    {
        "name": "list_tables",
        "description": "List all tables in the ClickHouse database",
        "risk_level": "LOW",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name",
                    "default": "dataforge",
                }
            },
        },
    },
    {
        "name": "describe_table",
        "description": "Get column definitions and types for a table",
        "risk_level": "LOW",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
                "database": {"type": "string", "default": "dataforge"},
            },
            "required": ["table"],
        },
    },
    {
        "name": "execute_select",
        "description": "Execute a read-only SELECT query (safety validated)",
        "risk_level": "LOW",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL SELECT query"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "profile_column",
        "description": "Profile a column: null rate, distinct count, min, max",
        "risk_level": "LOW",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
                "column": {"type": "string", "description": "Column name"},
            },
            "required": ["table", "column"],
        },
    },
    {
        "name": "get_recent_records",
        "description": "Get recent records from a table",
        "risk_level": "LOW",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["table"],
        },
    },
]

TOOL_MAP = {
    "list_tables": list_tables,
    "describe_table": describe_table,
    "execute_select": execute_select,
    "profile_column": profile_column,
    "get_recent_records": get_recent_records,
}
