"""Reliability Graph Pydantic schemas."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─── Node Schemas ─────────────────────────────────────────────────────


class NodeCreate(BaseModel):
    node_type: str = Field(
        ...,
        pattern=r"^(source|pipeline|table|column|query|dashboard|ml_model|business_process)$",
    )
    name: str = Field(..., min_length=1, max_length=500)
    external_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    project_id: Optional[uuid.UUID] = None
    owner_id: Optional[uuid.UUID] = None
    business_criticality: str = Field(
        default="medium", pattern=r"^(low|medium|high|critical)$"
    )


class NodeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=500)
    external_id: Optional[str] = None
    metadata: Optional[dict] = None
    project_id: Optional[uuid.UUID] = None
    owner_id: Optional[uuid.UUID] = None
    business_criticality: Optional[str] = Field(
        None, pattern=r"^(low|medium|high|critical)$"
    )


class NodeResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    project_id: Optional[uuid.UUID]
    node_type: str
    name: str
    external_id: Optional[str]
    metadata: dict = Field(validation_alias="extra_data")
    owner_id: Optional[uuid.UUID]
    business_criticality: str
    reliability_score: float
    last_incident_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Edge Schemas ─────────────────────────────────────────────────────


class EdgeCreate(BaseModel):
    source_id: uuid.UUID
    target_id: uuid.UUID
    edge_type: str = Field(
        ..., pattern=r"^(dependency|lineage|ownership|derivation|monitors)$"
    )
    metadata: dict = Field(default_factory=dict)


class EdgeResponse(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    edge_type: str
    metadata: dict = Field(validation_alias="extra_data")
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Graph Response Schemas ───────────────────────────────────────────


class GraphNode(BaseModel):
    id: uuid.UUID
    node_type: str
    name: str
    reliability_score: float
    business_criticality: str


class GraphEdge(BaseModel):
    source_id: uuid.UUID
    target_id: uuid.UUID
    edge_type: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# ─── Blast Radius Schema ─────────────────────────────────────────────


class BlastRadiusNode(BaseModel):
    id: str
    type: str
    name: str
    criticality: str


class BlastRadius(BaseModel):
    affected_nodes: list[BlastRadiusNode]
    total_affected: int
    business_impact: str
    affected_business_processes: list[str]
    affected_by_type: dict[str, int] = Field(default_factory=dict)


# ─── Reliability Score Schema ─────────────────────────────────────────


class ReliabilityScore(BaseModel):
    node_id: uuid.UUID
    score: float
    factors: dict[str, float]
    last_updated: datetime


# ─── Business Impact Schema ───────────────────────────────────────────


class BusinessImpact(BaseModel):
    impact_level: str
    impact_score: int
    affected_business_processes: list[str]
    recommended_actions: list[str]
