"""SQL safety layer — validates and restricts queries to read-only operations."""

import re

BLOCKED_KEYWORDS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "REPLACE",
    "GRANT",
    "REVOKE",
    "EXEC",
    "EXECUTE",
    "CALL",
    "MERGE",
    "ATTACH",
    "DETACH",
    "KILL",
    "SET",
    "OPTIMIZE",
    "ROTATE",
    "COMMENT",
]

FORBIDDEN_PATTERNS = [
    r";\s*\w",  # multiple statements
    r"UNION\s+ALL\s+SELECT.*INTO",  # SELECT INTO
    r"INTO\s+OUTFILE",
    r"INTO\s+DUMPFILE",
    r"LOAD\s+DATA",
    r"SYSTEM\s+",
]

MAX_QUERY_LENGTH = 5000
MAX_RESULT_ROWS = 10000


class SQLSafetyError(Exception):
    """Raised when a query violates safety constraints."""

    pass


def validate_query(query: str) -> str:
    """Validate and sanitize a SQL query for read-only execution.

    Returns the cleaned query if valid, raises SQLSafetyError otherwise.
    """
    if not query or not query.strip():
        raise SQLSafetyError("Empty query")

    cleaned = query.strip().rstrip(";").strip()

    if len(cleaned) > MAX_QUERY_LENGTH:
        raise SQLSafetyError(f"Query exceeds max length of {MAX_QUERY_LENGTH}")

    upper = cleaned.upper()

    for keyword in BLOCKED_KEYWORDS:
        pattern = r"\b" + keyword + r"\b"
        if re.search(pattern, upper):
            raise SQLSafetyError(f"Blocked keyword: {keyword}")

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, upper):
            raise SQLSafetyError(f"Forbidden pattern detected: {pattern}")

    if not upper.startswith("SELECT"):
        raise SQLSafetyError("Only SELECT queries are allowed")

    return cleaned


def add_row_limit(query: str, limit: int = MAX_RESULT_ROWS) -> str:
    """Add a LIMIT clause if not already present."""
    upper = query.upper()
    if "LIMIT" not in upper:
        query = f"{query.rstrip()} LIMIT {limit}"
    return query
