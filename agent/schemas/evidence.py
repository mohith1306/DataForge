from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    source: str = Field(..., description="Source system: database, pipeline, github, sandbox")
    type: str = Field(..., description="Evidence type: schema, metric, log, commit, analysis")
    content: dict = Field(..., description="Evidence content")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Confidence in this evidence")


class InvestigationResult(BaseModel):
    agent: str = Field(..., description="Agent that produced this result")
    findings: list[EvidenceItem] = Field(default_factory=list)
    summary: str = Field("", description="Brief summary of findings")
    errors: list[str] = Field(default_factory=list)


class RootCauseResult(BaseModel):
    root_cause: str = Field(..., description="Description of root cause")
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    business_impact: dict = Field(default_factory=dict)
