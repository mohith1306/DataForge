"""Agent orchestrator for multi-agent workflows."""
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from enum import Enum

from .base import BaseAgent, AgentMessage, AgentResult
from .specialized import (
    DiagnosisAgent,
    InvestigationAgent,
    ImpactAgent,
    RepairAgent,
    PreventionAgent,
)


class WorkflowType(str, Enum):
    """Types of investigation workflows."""
    FULL_INVESTIGATION = "full_investigation"
    QUICK_DIAGNOSIS = "quick_diagnosis"
    IMPACT_ASSESSMENT = "impact_assessment"
    REMEDIATION_ONLY = "remediation_only"
    PREVENTION_REVIEW = "prevention_review"


class WorkflowStatus(str, Enum):
    """Status of a workflow."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"


class AgentOrchestrator:
    """Orchestrates multi-agent workflows for incident investigation."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.agents: Dict[str, BaseAgent] = {}
        self.workflows: Dict[str, Dict[str, Any]] = {}
        self._initialize_agents()

    def _initialize_agents(self) -> None:
        """Initialize all specialized agents."""
        agent_classes = [
            DiagnosisAgent,
            InvestigationAgent,
            ImpactAgent,
            RepairAgent,
            PreventionAgent,
        ]
        
        for agent_class in agent_classes:
            agent = agent_class(config=self.config)
            self.agents[agent.agent_type] = agent

    def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """Get an agent by type."""
        return self.agents.get(agent_type)

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all available agents and their capabilities."""
        return [
            {
                "agent_type": agent.agent_type,
                "agent_id": agent.agent_id,
                "capabilities": agent.get_capabilities(),
            }
            for agent in self.agents.values()
        ]

    def create_workflow(
        self,
        workflow_type: WorkflowType,
        incident_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new investigation workflow."""
        workflow_id = str(uuid4())
        
        # Define workflow steps based on type
        steps = self._get_workflow_steps(workflow_type)
        
        self.workflows[workflow_id] = {
            "id": workflow_id,
            "type": workflow_type,
            "status": WorkflowStatus.PENDING,
            "incident_data": incident_data,
            "context": context or {},
            "steps": steps,
            "current_step": 0,
            "results": {},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        
        return workflow_id

    def _get_workflow_steps(self, workflow_type: WorkflowType) -> List[str]:
        """Get workflow steps based on type."""
        workflow_steps = {
            WorkflowType.FULL_INVESTIGATION: [
                "diagnosis",
                "investigation",
                "impact",
                "repair",
                "prevention",
            ],
            WorkflowType.QUICK_DIAGNOSIS: [
                "diagnosis",
                "impact",
            ],
            WorkflowType.IMPACT_ASSESSMENT: [
                "impact",
            ],
            WorkflowType.REMEDIATION_ONLY: [
                "diagnosis",
                "repair",
            ],
            WorkflowType.PREVENTION_REVIEW: [
                "investigation",
                "prevention",
            ],
        }
        return workflow_steps.get(workflow_type, [])

    async def execute_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Execute a workflow and return results."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return {"error": "Workflow not found"}
        
        workflow["status"] = WorkflowStatus.RUNNING
        workflow["updated_at"] = datetime.now(timezone.utc)
        
        results = {}
        
        try:
            for i, step in enumerate(workflow["steps"]):
                workflow["current_step"] = i
                
                # Get context from previous steps
                context = {
                    "incident": workflow["incident_data"],
                    **workflow["context"],
                    **results,
                }
                
                # Execute the agent
                agent = self.agents.get(step)
                if not agent:
                    results[step] = {
                        "error": f"Agent {step} not found",
                        "success": False,
                    }
                    continue
                
                result = await agent.process(context)
                results[step] = {
                    "success": result.success,
                    "data": result.data,
                    "recommendations": result.recommendations,
                    "confidence": result.confidence,
                    "execution_time_ms": result.execution_time_ms,
                }
                
                # Send messages between agents
                if i > 0:
                    prev_step = workflow["steps"][i - 1]
                    message = agent.send_message(
                        recipient=step,
                        content={"previous_result": results[prev_step]},
                        message_type="workflow_context",
                    )
            
            workflow["results"] = results
            workflow["status"] = WorkflowStatus.COMPLETED
            
        except Exception as e:
            workflow["status"] = WorkflowStatus.FAILED
            workflow["error"] = str(e)
            results["error"] = str(e)
        
        workflow["updated_at"] = datetime.now(timezone.utc)
        
        return {
            "workflow_id": workflow_id,
            "status": workflow["status"],
            "results": results,
            "total_execution_time_ms": sum(
                r.get("execution_time_ms", 0)
                for r in results.values()
                if isinstance(r, dict)
            ),
        }

    def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a workflow."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return None
        
        return {
            "id": workflow["id"],
            "type": workflow["type"],
            "status": workflow["status"],
            "current_step": workflow["current_step"],
            "total_steps": len(workflow["steps"]),
            "created_at": workflow["created_at"].isoformat(),
            "updated_at": workflow["updated_at"].isoformat(),
        }

    def get_workflow_results(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get the results of a completed workflow."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return None
        
        return {
            "workflow_id": workflow_id,
            "status": workflow["status"],
            "results": workflow["results"],
        }

    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a running workflow."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return False
        
        if workflow["status"] == WorkflowStatus.RUNNING:
            workflow["status"] = WorkflowStatus.FAILED
            workflow["error"] = "Workflow cancelled by user"
            workflow["updated_at"] = datetime.now(timezone.utc)
            return True
        
        return False
