import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class IncidentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    severity: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    incident_type: str | None = None


class IncidentResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    severity: str
    status: str
    incident_type: str | None
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class IncidentEventResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    type: str
    agent: str | None
    tool: str | None
    message: str | None
    metadata_: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    source: str
    type: str
    content: dict
    confidence: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalRequest(BaseModel):
    reviewer: str = Field(..., min_length=1)


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    action: str
    status: str
    reviewer: str | None
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}
