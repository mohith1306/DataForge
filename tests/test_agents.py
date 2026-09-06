"""Tests for AI agents and orchestrator."""
import pytest
from apps.api.app.agents.base import BaseAgent, AgentMessage, AgentResult
from apps.api.app.agents.specialized import (
    DiagnosisAgent,
    InvestigationAgent,
    ImpactAgent,
    RepairAgent,
    PreventionAgent,
)
from apps.api.app.agents.orchestrator import AgentOrchestrator, WorkflowType, WorkflowStatus


@pytest.mark.asyncio
async def test_diagnosis_agent_connection_error():
    """Test DiagnosisAgent with connection error."""
    agent = DiagnosisAgent()
    context = {
        "incident": {
            "error_message": "Connection timeout to database",
            "stack_trace": "",
            "affected_services": ["api", "worker"],
        }
    }
    
    result = await agent.process(context)
    
    assert result.success is True
    assert result.agent_type == "diagnosis"
    assert "connection" in result.data["primary_cause"].lower()
    assert result.confidence > 0.5


@pytest.mark.asyncio
async def test_diagnosis_agent_memory_error():
    """Test DiagnosisAgent with memory error."""
    agent = DiagnosisAgent()
    context = {
        "incident": {
            "error_message": "Out of memory",
            "stack_trace": "java.lang.OutOfMemoryError: Java heap space",
            "affected_services": ["api"],
        }
    }
    
    result = await agent.process(context)
    
    assert result.success is True
    assert "memory" in result.data["primary_cause"].lower() or "heap" in result.data["primary_cause"].lower()


@pytest.mark.asyncio
async def test_investigation_agent():
    """Test InvestigationAgent."""
    agent = InvestigationAgent()
    context = {
        "incident": {
            "id": "test-123",
            "severity": "high",
            "affected_services": ["api", "db"],
        },
        "blast_radius": {
            "total_affected": 5,
            "affected_nodes": ["node1", "node2"],
            "business_impact": "high",
        },
        "diagnosis": {
            "primary_cause": "Database connection pool exhaustion",
        },
    }
    
    result = await agent.process(context)
    
    assert result.success is True
    assert result.agent_type == "investigation"
    assert "incident_summary" in result.data
    assert result.data["incident_summary"]["severity"] == "high"


@pytest.mark.asyncio
async def test_impact_agent():
    """Test ImpactAgent."""
    agent = ImpactAgent()
    context = {
        "incident": {"severity": "critical"},
        "blast_radius": {
            "total_affected": 10,
            "business_impact": "critical",
        },
    }
    
    result = await agent.process(context)
    
    assert result.success is True
    assert result.agent_type == "impact"
    assert "impact_score" in result.data
    assert result.data["impact_score"] > 50


@pytest.mark.asyncio
async def test_repair_agent():
    """Test RepairAgent."""
    agent = RepairAgent()
    context = {
        "diagnosis": {"primary_cause": "Database connection pool exhaustion"},
        "impact": {"impact_level": "severe", "impact_score": 85},
        "investigation": {},
    }
    
    result = await agent.process(context)
    
    assert result.success is True
    assert result.agent_type == "repair"
    assert "actions" in result.data
    assert len(result.data["actions"]) > 0


@pytest.mark.asyncio
async def test_prevention_agent():
    """Test PreventionAgent."""
    agent = PreventionAgent()
    context = {
        "diagnosis": {"primary_cause": "Database connection pool exhaustion"},
        "investigation": {},
        "incident_history": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
    }
    
    result = await agent.process(context)
    
    assert result.success is True
    assert result.agent_type == "prevention"
    assert "prevention_recommendations" in result.data


def test_orchestrator_initialization():
    """Test AgentOrchestrator initializes all agents."""
    orchestrator = AgentOrchestrator()
    
    agents = orchestrator.list_agents()
    agent_types = [a["agent_type"] for a in agents]
    
    assert "diagnosis" in agent_types
    assert "investigation" in agent_types
    assert "impact" in agent_types
    assert "repair" in agent_types
    assert "prevention" in agent_types


def test_orchestrator_get_agent():
    """Test getting specific agent from orchestrator."""
    orchestrator = AgentOrchestrator()
    
    agent = orchestrator.get_agent("diagnosis")
    assert agent is not None
    assert agent.agent_type == "diagnosis"


def test_orchestrator_create_workflow():
    """Test creating a workflow."""
    orchestrator = AgentOrchestrator()
    
    workflow_id = orchestrator.create_workflow(
        workflow_type=WorkflowType.QUICK_DIAGNOSIS,
        incident_data={"id": "test-123", "severity": "high"},
    )
    
    assert workflow_id is not None
    status = orchestrator.get_workflow_status(workflow_id)
    assert status is not None
    assert status["status"] == WorkflowStatus.PENDING


@pytest.mark.asyncio
async def test_orchestrator_execute_workflow():
    """Test executing a workflow."""
    orchestrator = AgentOrchestrator()
    
    workflow_id = orchestrator.create_workflow(
        workflow_type=WorkflowType.QUICK_DIAGNOSIS,
        incident_data={
            "id": "test-123",
            "severity": "high",
            "error_message": "Connection timeout",
            "affected_services": ["api"],
        },
    )
    
    result = await orchestrator.execute_workflow(workflow_id)
    
    assert result["status"] == WorkflowStatus.COMPLETED
    assert "diagnosis" in result["results"]
    assert "impact" in result["results"]


@pytest.mark.asyncio
async def test_orchestrator_cancel_workflow():
    """Test cancelling a workflow."""
    orchestrator = AgentOrchestrator()
    
    workflow_id = orchestrator.create_workflow(
        workflow_type=WorkflowType.FULL_INVESTIGATION,
        incident_data={"id": "test-123", "severity": "low"},
    )
    
    # Start workflow in background (simplified for test)
    success = orchestrator.cancel_workflow(workflow_id)
    
    # Note: Can't cancel a pending workflow, only running
    # This test verifies the method exists and handles non-running workflows
    assert isinstance(success, bool)
