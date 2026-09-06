"""API endpoints for policy management and AI agent orchestration."""
from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.auth import get_current_user, UserContext
from ..core.policy_engine import Policy, PolicyEngine, PolicyType
from ..core.risk_classifier import EnhancedRiskClassifier
from ..agents.orchestrator import AgentOrchestrator, WorkflowType

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Singleton instances
_policy_engine = PolicyEngine()
_risk_classifier = EnhancedRiskClassifier(_policy_engine)
_agent_orchestrator = AgentOrchestrator()


# Pydantic models
class PolicyCreate(BaseModel):
    name: str
    policy_type: str
    rules: List[Dict[str, Any]]
    description: str = ""
    enabled: bool = True


class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    rules: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None


class ActionValidation(BaseModel):
    action_type: str
    parameters: Dict[str, Any] = {}


class WorkflowCreate(BaseModel):
    workflow_type: str
    incident_data: Dict[str, Any]
    context: Dict[str, Any] = {}


# Policy endpoints
@router.get("/policies")
async def list_policies(
    policy_type: Optional[str] = None,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """List all policies."""
    pt = PolicyType(policy_type) if policy_type else None
    policies = _policy_engine.list_policies(pt)
    return {
        "policies": policies,
        "summary": _policy_engine.get_policy_summary(),
    }


@router.post("/policies")
async def create_policy(
    policy_data: PolicyCreate,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Create a new policy."""
    policy = Policy(
        name=policy_data.name,
        policy_type=PolicyType(policy_data.policy_type),
        rules=policy_data.rules,
        description=policy_data.description,
        enabled=policy_data.enabled,
    )
    _policy_engine.add_policy(policy)
    return {"policy": policy.to_dict(), "message": "Policy created"}


@router.put("/policies/{policy_id}")
async def update_policy(
    policy_id: str,
    policy_data: PolicyUpdate,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update an existing policy."""
    policy = _policy_engine.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    if policy_data.name is not None:
        policy.name = policy_data.name
    if policy_data.rules is not None:
        policy.rules = policy_data.rules
    if policy_data.description is not None:
        policy.description = policy_data.description
    if policy_data.enabled is not None:
        policy.enabled = policy_data.enabled
    
    policy.updated_at = datetime.now(timezone.utc)
    
    return {"policy": policy.to_dict(), "message": "Policy updated"}


@router.delete("/policies/{policy_id}")
async def delete_policy(
    policy_id: str,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Delete a policy."""
    success = _policy_engine.remove_policy(policy_id)
    if not success:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"message": "Policy deleted"}


# Risk classification endpoints
@router.post("/risk/classify")
async def classify_action_risk(
    action: ActionValidation,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Classify the risk of an action."""
    action_dict = {
        "action_type": action.action_type,
        "parameters": action.parameters,
    }
    
    classification = _risk_classifier.classify_remediation(action_dict)
    recommendations = _risk_classifier.get_risk_recommendations(classification)
    
    return {
        "classification": classification,
        "recommendations": recommendations,
    }


@router.post("/risk/classify-multiple")
async def classify_multiple_actions_risk(
    actions: List[ActionValidation],
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Classify risk for multiple actions."""
    action_dicts = [
        {"action_type": a.action_type, "parameters": a.parameters}
        for a in actions
    ]
    
    result = _risk_classifier.classify_multiple_actions(action_dicts)
    
    # Get recommendations for aggregate result
    aggregate_classification = {
        "risk_level": result["aggregate"]["max_risk_level"],
        "requires_approval": result["aggregate"]["requires_approval"],
        "constraints": result["aggregate"]["unique_constraints"],
    }
    recommendations = _risk_classifier.get_risk_recommendations(aggregate_classification)
    
    return {
        **result,
        "recommendations": recommendations,
    }


# Action validation endpoint
@router.post("/validate-action")
async def validate_action(
    action: ActionValidation,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Validate an action against all policies."""
    action_dict = {
        "action_type": action.action_type,
        "parameters": action.parameters,
    }
    
    validation = _policy_engine.validate_action(action_dict)
    
    return validation


# Agent endpoints
@router.get("/agents")
async def list_agents(
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """List all available AI agents."""
    agents = _agent_orchestrator.list_agents()
    return {"agents": agents}


@router.get("/agents/{agent_type}")
async def get_agent_info(
    agent_type: str,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get information about a specific agent."""
    agent = _agent_orchestrator.get_agent(agent_type)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return {
        "agent_type": agent.agent_type,
        "agent_id": agent.agent_id,
        "capabilities": agent.get_capabilities(),
        "history": agent.get_history(),
    }


# Workflow endpoints
@router.post("/workflows")
async def create_workflow(
    workflow_data: WorkflowCreate,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Create a new investigation workflow."""
    try:
        workflow_type = WorkflowType(workflow_data.workflow_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workflow type")
    
    workflow_id = _agent_orchestrator.create_workflow(
        workflow_type=workflow_type,
        incident_data=workflow_data.incident_data,
        context=workflow_data.context,
    )
    
    return {
        "workflow_id": workflow_id,
        "message": "Workflow created",
    }


@router.post("/workflows/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Execute a workflow."""
    result = await _agent_orchestrator.execute_workflow(workflow_id)
    
    if "error" in result and result.get("status") == "failed":
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result


@router.get("/workflows/{workflow_id}")
async def get_workflow_status(
    workflow_id: str,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get workflow status."""
    status = _agent_orchestrator.get_workflow_status(workflow_id)
    if not status:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return status


@router.get("/workflows/{workflow_id}/results")
async def get_workflow_results(
    workflow_id: str,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get workflow results."""
    results = _agent_orchestrator.get_workflow_results(workflow_id)
    if not results:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return results


@router.post("/workflows/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: str,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Cancel a running workflow."""
    success = _agent_orchestrator.cancel_workflow(workflow_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel workflow")
    return {"message": "Workflow cancelled"}
