"""Intelligence API endpoints for incident correlation, deduplication, and blast radius."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..core.auth import get_current_user, require_read, require_write
from ..core.tenant import UserContext
from ..intelligence.correlation import IncidentCorrelation, CorrelationRule, CorrelationStrategy
from ..intelligence.deduplication import IncidentDeduplication, DeduplicationStrategy
from ..intelligence.blast_radius import BlastRadiusCalculator

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

# Singleton instances
_correlation = IncidentCorrelation()
_deduplication = IncidentDeduplication()
_blast_radius = BlastRadiusCalculator()


class CorrelateRequest(BaseModel):
    """Request to correlate incidents."""
    incidents: List[Dict[str, Any]]
    strategy: CorrelationStrategy = CorrelationStrategy.SERVICE


class DeduplicateRequest(BaseModel):
    """Request to check for duplicates."""
    incident: Dict[str, Any]
    strategy: DeduplicationStrategy = DeduplicationStrategy.SIGNATURE_MATCH


class BlastRadiusRequest(BaseModel):
    """Request to calculate blast radius."""
    incident: Dict[str, Any]
    affected_services: Optional[List[str]] = None


class RegisterEntityRequest(BaseModel):
    """Request to register an entity for blast radius calculation."""
    entity_id: str
    entity_type: str
    dependencies: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


# Correlation endpoints
@router.post("/correlate")
async def correlate_incidents(
    request: CorrelateRequest,
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Correlate incidents using specified strategy."""
    results = _correlation.correlate(request.incidents, request.strategy)
    return {"correlations": [r.model_dump() for r in results]}


@router.get("/correlations")
async def list_correlations(
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """List all correlations."""
    correlations = _correlation.list_correlations()
    return {"correlations": [c.model_dump() for c in correlations]}


@router.get("/correlations/{correlation_id}")
async def get_correlation(
    correlation_id: str,
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Get a specific correlation."""
    correlation = _correlation.get_correlation(correlation_id)
    if not correlation:
        raise HTTPException(status_code=404, detail="Correlation not found")
    return {"correlation": correlation.model_dump()}


@router.get("/correlations/incident/{incident_id}")
async def get_correlations_for_incident(
    incident_id: str,
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Get all correlations for an incident."""
    correlations = _correlation.get_correlations_for_incident(incident_id)
    return {"correlations": [c.model_dump() for c in correlations]}


# Deduplication endpoints
@router.post("/deduplicate")
async def check_duplicate(
    request: DeduplicateRequest,
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Check if an incident is a duplicate."""
    _deduplication.add_incident(request.incident)
    result = _deduplication.check_duplicate(request.incident, request.strategy)
    if result:
        return {"is_duplicate": True, "result": result.model_dump()}
    return {"is_duplicate": False}


@router.post("/deduplicate/add")
async def add_incident_to_dedup(
    incident: Dict[str, Any],
    user: UserContext = Depends(require_write),
) -> Dict[str, Any]:
    """Add an incident to the deduplication index."""
    _deduplication.add_incident(incident)
    return {"message": "Incident added to deduplication index"}


@router.get("/deduplication/results")
async def list_deduplication_results(
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """List all deduplication results."""
    results = _deduplication.list_deduplication_results()
    return {"results": [r.model_dump() for r in results]}


@router.get("/deduplication/stats")
async def get_deduplication_stats(
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Get deduplication statistics."""
    return _deduplication.get_stats()


# Blast radius endpoints
@router.post("/blast-radius")
async def calculate_blast_radius(
    request: BlastRadiusRequest,
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Calculate blast radius for an incident."""
    result = _blast_radius.calculate(request.incident, request.affected_services)
    return {"blast_radius": result.model_dump()}


@router.post("/blast-radius/entities")
async def register_entity(
    request: RegisterEntityRequest,
    user: UserContext = Depends(require_write),
) -> Dict[str, Any]:
    """Register an entity for blast radius calculation."""
    _blast_radius.register_entity(
        entity_id=request.entity_id,
        entity_type=request.entity_type,
        dependencies=request.dependencies,
        metadata=request.metadata
    )
    return {"message": "Entity registered"}


@router.get("/blast-radius/dependencies/{entity_id}")
async def get_dependencies(
    entity_id: str,
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Get dependency chain for an entity."""
    chain = _blast_radius.get_dependency_chain(entity_id)
    return {"entity_id": entity_id, "dependencies": chain}


@router.get("/blast-radius/dependents/{entity_id}")
async def get_dependents(
    entity_id: str,
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Get all entities that depend on this entity."""
    dependents = _blast_radius.get_dependents(entity_id)
    return {"entity_id": entity_id, "dependents": dependents}


@router.get("/blast-radius/stats")
async def get_blast_radius_stats(
    user: UserContext = Depends(require_read),
) -> Dict[str, Any]:
    """Get blast radius calculator statistics."""
    return _blast_radius.get_stats()
