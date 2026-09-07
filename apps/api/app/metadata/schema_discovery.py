"""Schema Discovery for automatic schema detection and cataloging."""
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from enum import Enum


class FieldType(str, Enum):
    """Supported field types."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    ARRAY = "array"
    OBJECT = "object"
    UNKNOWN = "unknown"


class SchemaField(BaseModel):
    """A field in a discovered schema."""
    name: str
    field_type: FieldType
    nullable: bool = True
    description: Optional[str] = None
    sample_values: List[Any] = []
    constraints: Dict[str, Any] = {}
    confidence: float = 0.8


class DiscoveredSchema(BaseModel):
    """A discovered schema from a data source."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    source_type: str  # database, api, file, etc.
    source_id: str
    fields: List[SchemaField] = []
    row_count: Optional[int] = None
    last_discovered: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = {}


class SchemaDiscovery:
    """Discovers and catalogs schemas from various data sources."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.schemas: Dict[str, DiscoveredSchema] = {}
        self.source_schemas: Dict[str, List[str]] = {}  # source_id -> schema_ids

    def discover_from_dict(
        self,
        name: str,
        source_id: str,
        data: List[Dict[str, Any]],
        sample_size: int = 100
    ) -> DiscoveredSchema:
        """Discover schema from a list of dictionaries."""
        if not data:
            return DiscoveredSchema(
                name=name,
                source_type="dict",
                source_id=source_id,
                fields=[]
            )

        sample = data[:sample_size]
        fields = []

        # Get all unique keys
        all_keys = set()
        for row in sample:
            all_keys.update(row.keys())

        for key in all_keys:
            values = [row.get(key) for row in sample if key in row]
            field = self._infer_field(key, values)
            fields.append(field)

        schema = DiscoveredSchema(
            name=name,
            source_type="dict",
            source_id=source_id,
            fields=fields,
            row_count=len(data),
            metadata={"sample_size": len(sample)}
        )

        self.schemas[schema.id] = schema
        if source_id not in self.source_schemas:
            self.source_schemas[source_id] = []
        self.source_schemas[source_id].append(schema.id)

        return schema

    def discover_from_columns(
        self,
        name: str,
        source_id: str,
        columns: List[str],
        sample_data: Optional[List[List[Any]]] = None
    ) -> DiscoveredSchema:
        """Discover schema from column names and optional sample data."""
        fields = []

        for col in columns:
            if sample_data:
                values = [row[columns.index(col)] for row in sample_data if col in columns]
            else:
                values = []

            field = self._infer_field(col, values)
            fields.append(field)

        schema = DiscoveredSchema(
            name=name,
            source_type="columns",
            source_id=source_id,
            fields=fields,
            metadata={"columns": columns}
        )

        self.schemas[schema.id] = schema
        if source_id not in self.source_schemas:
            self.source_schemas[source_id] = []
        self.source_schemas[source_id].append(schema.id)

        return schema

    def _infer_field(self, name: str, values: List[Any]) -> SchemaField:
        """Infer field type from values."""
        if not values:
            return SchemaField(name=name, field_type=FieldType.UNKNOWN, nullable=True)

        non_null = [v for v in values if v is not None]
        nullable = len(non_null) < len(values)

        if not non_null:
            return SchemaField(name=name, field_type=FieldType.UNKNOWN, nullable=nullable)

        # Check types
        type_counts = {FieldType.STRING: 0, FieldType.INTEGER: 0, FieldType.FLOAT: 0,
                      FieldType.BOOLEAN: 0, FieldType.DATETIME: 0, FieldType.DATE: 0}

        for v in non_null:
            if isinstance(v, bool):
                type_counts[FieldType.BOOLEAN] += 1
            elif isinstance(v, int):
                type_counts[FieldType.INTEGER] += 1
            elif isinstance(v, float):
                type_counts[FieldType.FLOAT] += 1
            elif isinstance(v, str):
                # Check if it's a date/datetime string
                if self._is_datetime(v):
                    type_counts[FieldType.DATETIME] += 1
                elif self._is_date(v):
                    type_counts[FieldType.DATE] += 1
                else:
                    type_counts[FieldType.STRING] += 1

        # Find dominant type
        dominant_type = max(type_counts, key=type_counts.get)
        confidence = type_counts[dominant_type] / len(non_null)

        # Get sample values
        sample_values = non_null[:5]

        return SchemaField(
            name=name,
            field_type=dominant_type,
            nullable=nullable,
            sample_values=sample_values,
            confidence=confidence
        )

    def _is_datetime(self, value: str) -> bool:
        """Check if string looks like datetime."""
        datetime_formats = [
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f"
        ]
        for fmt in datetime_formats:
            try:
                datetime.strptime(value, fmt)
                return True
            except ValueError:
                continue
        return False

    def _is_date(self, value: str) -> bool:
        """Check if string looks like date."""
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def get_schema(self, schema_id: str) -> Optional[DiscoveredSchema]:
        """Get schema by ID."""
        return self.schemas.get(schema_id)

    def get_schemas_for_source(self, source_id: str) -> List[DiscoveredSchema]:
        """Get all schemas for a source."""
        schema_ids = self.source_schemas.get(source_id, [])
        return [self.schemas[sid] for sid in schema_ids if sid in self.schemas]

    def list_schemas(self) -> List[DiscoveredSchema]:
        """List all discovered schemas."""
        return list(self.schemas.values())

    def compare_schemas(self, schema_id1: str, schema_id2: str) -> Dict[str, Any]:
        """Compare two schemas and find differences."""
        schema1 = self.schemas.get(schema_id1)
        schema2 = self.schemas.get(schema_id2)

        if not schema1 or not schema2:
            return {"error": "Schema not found"}

        fields1 = {f.name: f for f in schema1.fields}
        fields2 = {f.name: f for f in schema2.fields}

        common = set(fields1.keys()) & set(fields2.keys())
        only_in_1 = set(fields1.keys()) - set(fields2.keys())
        only_in_2 = set(fields2.keys()) - set(fields1.keys())

        type_mismatches = []
        for field_name in common:
            if fields1[field_name].field_type != fields2[field_name].field_type:
                type_mismatches.append({
                    "field": field_name,
                    "type1": fields1[field_name].field_type.value,
                    "type2": fields2[field_name].field_type.value
                })

        return {
            "schema1": schema_id1,
            "schema2": schema_id2,
            "common_fields": list(common),
            "only_in_schema1": list(only_in_1),
            "only_in_schema2": list(only_in_2),
            "type_mismatches": type_mismatches,
            "similarity": len(common) / max(len(fields1), len(fields2), 1)
        }
