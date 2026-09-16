"""SQL Lineage Parser — Extracts table/column lineage from SQL queries.

Uses regex-based parsing for common SQL patterns. Supports:
- SELECT ... FROM ... (reads_from)
- INSERT INTO ... SELECT ... (writes_to / transforms)
- CREATE TABLE ... AS SELECT ... (creates)
- JOIN relationships
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TableRef:
    """A reference to a table in SQL."""
    database: str = ""
    schema: str = ""
    table: str = ""
    alias: str = ""

    @property
    def full_name(self) -> str:
        parts = [p for p in [self.database, self.schema, self.table] if p]
        return ".".join(parts)

    @property
    def display_name(self) -> str:
        return self.table or self.full_name


@dataclass
class LineageEdge:
    """A lineage relationship between two tables."""
    source: str
    target: str
    transformation: str  # select, join, aggregate, union, cte, subquery
    columns: list[str] = field(default_factory=list)
    sql_snippet: str = ""


class SQLLineageParser:
    """Extracts lineage from SQL queries."""

    # Common SQL keywords that indicate table references
    _FROM_PATTERN = re.compile(
        r'\bFROM\s+([`\w."]+(?:\s+(?:AS\s+)?(\w+))?)',
        re.IGNORECASE,
    )
    _JOIN_PATTERN = re.compile(
        r'\bJOIN\s+([`\w."]+(?:\s+(?:AS\s+)?(\w+))?)',
        re.IGNORECASE,
    )
    _INTO_PATTERN = re.compile(
        r'\bINTO\s+([`\w."]+)',
        re.IGNORECASE,
    )
    _CREATE_AS_PATTERN = re.compile(
        r'\bCREATE\s+(?:TEMPORARY\s+|TEMP\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\w."]+)\s+AS\s+SELECT',
        re.IGNORECASE,
    )
    _INSERT_SELECT_PATTERN = re.compile(
        r'\bINSERT\s+(?:INTO|OVERWRITE)\s+([`\w."]+)\s+.*?\bSELECT\b',
        re.IGNORECASE,
    )
    _CTE_PATTERN = re.compile(
        r'\bWITH\s+(?:RECURSIVE\s+)?(\w+)\s+AS\s*\(',
        re.IGNORECASE,
    )
    _SUBQUERY_PATTERN = re.compile(
        r'\(\s*SELECT\b',
        re.IGNORECASE,
    )

    def parse(self, sql: str) -> dict:
        """Parse a SQL query and extract lineage.

        Returns:
            {
                "source_tables": [TableRef, ...],
                "target_tables": [TableRef, ...],
                "lineage_edges": [LineageEdge, ...],
                "ctes": [str, ...],
                "has_subqueries": bool,
            }
        """
        source_tables = []
        target_tables = []
        lineage_edges = []
        ctes = []

        # Extract CTEs
        for match in self._CTE_PATTERN.finditer(sql):
            ctes.append(match.group(1))

        # Extract FROM tables (sources)
        for match in self._FROM_PATTERN.finditer(sql):
            table_ref = self._parse_table_ref(match.group(1))
            alias = match.group(2) if match.lastindex >= 2 else ""
            if alias:
                table_ref.alias = alias
            source_tables.append(table_ref)

        # Extract JOIN tables (also sources)
        for match in self._JOIN_PATTERN.finditer(sql):
            table_ref = self._parse_table_ref(match.group(1))
            alias = match.group(2) if match.lastindex >= 2 else ""
            if alias:
                table_ref.alias = alias
            source_tables.append(table_ref)

        # Extract INSERT INTO targets
        for match in self._INTO_PATTERN.finditer(sql):
            # Skip if it's part of INSERT ... SELECT (handled below)
            target_tables.append(self._parse_table_ref(match.group(1)))

        # Extract CREATE TABLE AS targets
        for match in self._CREATE_AS_PATTERN.finditer(sql):
            target_tables.append(self._parse_table_ref(match.group(1)))

        # Extract INSERT ... SELECT targets
        for match in self._INSERT_SELECT_PATTERN.finditer(sql):
            target_tables.append(self._parse_table_ref(match.group(1)))

        # Deduplicate
        source_tables = self._dedup_tables(source_tables)
        target_tables = self._dedup_tables(target_tables)

        # Build lineage edges
        for source in source_tables:
            for target in target_tables:
                transformation = self._infer_transformation(sql)
                edge = LineageEdge(
                    source=source.full_name,
                    target=target.full_name,
                    transformation=transformation,
                    sql_snippet=sql[:500],
                )
                lineage_edges.append(edge)

        return {
            "source_tables": source_tables,
            "target_tables": target_tables,
            "lineage_edges": lineage_edges,
            "ctes": ctes,
            "has_subqueries": bool(self._SUBQUERY_PATTERN.search(sql)),
        }

    def _parse_table_ref(self, raw: str) -> TableRef:
        """Parse a raw table reference like 'schema.table' or '`db`.`schema`.`table`'."""
        # Remove backticks and quotes
        cleaned = raw.strip().replace("`", "").replace('"', "").strip()

        # Remove alias suffix (e.g., "table AS t" already handled by regex)
        parts = cleaned.split()
        table_part = parts[0] if parts else cleaned

        # Split by dots
        segments = table_part.split(".")
        segments = [s for s in segments if s]  # Remove empty

        if len(segments) == 3:
            return TableRef(database=segments[0], schema=segments[1], table=segments[2])
        elif len(segments) == 2:
            return TableRef(schema=segments[0], table=segments[1])
        elif len(segments) == 1:
            return TableRef(table=segments[0])
        else:
            return TableRef(table=table_part)

    def _dedup_tables(self, tables: list[TableRef]) -> list[TableRef]:
        """Deduplicate tables by full_name."""
        seen = set()
        result = []
        for t in tables:
            key = t.full_name
            if key not in seen:
                seen.add(key)
                result.append(t)
        return result

    def _infer_transformation(self, sql: str) -> str:
        """Infer the transformation type from SQL patterns."""
        sql_upper = sql.upper()
        if "GROUP BY" in sql_upper:
            return "aggregate"
        if "UNION" in sql_upper:
            return "union"
        if "JOIN" in sql_upper:
            return "join"
        if "WITH" in sql_upper and "AS (" in sql_upper:
            return "cte"
        if "WHERE" in sql_upper:
            return "select"
        return "select"

    def parse_batch(self, queries: list[str]) -> dict:
        """Parse multiple SQL queries and aggregate lineage.

        Returns:
            {
                "all_source_tables": [str, ...],
                "all_target_tables": [str, ...],
                "all_edges": [LineageEdge, ...],
                "query_count": int,
            }
        """
        all_sources = set()
        all_targets = set()
        all_edges = []

        for sql in queries:
            result = self.parse(sql)
            for t in result["source_tables"]:
                all_sources.add(t.full_name)
            for t in result["target_tables"]:
                all_targets.add(t.full_name)
            all_edges.extend(result["lineage_edges"])

        return {
            "all_source_tables": sorted(all_sources),
            "all_target_tables": sorted(all_targets),
            "all_edges": all_edges,
            "query_count": len(queries),
        }
