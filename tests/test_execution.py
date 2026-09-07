"""Tests for Execution Fabric."""
import pytest
from apps.api.app.execution.base import ExecutionStatus, RollbackInfo
from apps.api.app.execution.executors import (
    DbtExecutor,
    AirflowExecutor,
    K8sExecutor,
    GithubExecutor,
    SqlExecutor,
    CloudApiExecutor,
)
from apps.api.app.execution.fabric import ExecutionFabric


@pytest.mark.asyncio
async def test_dbt_executor_execute():
    """Test DbtExecutor execution."""
    executor = DbtExecutor()
    
    action = {
        "action_type": "dbt",
        "command": "run",
        "models": "my_model",
    }
    
    result = await executor.execute(action, {})
    
    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED
    assert "rows_affected" in result.output


@pytest.mark.asyncio
async def test_dbt_executor_rollback():
    """Test DbtExecutor rollback."""
    executor = DbtExecutor()
    
    action = {
        "execution_id": "test-123",
        "action_type": "dbt",
        "command": "run",
    }
    
    # Execute first
    await executor.execute(action, {})
    
    # Get rollback info
    rollback_info = executor.get_rollback_info("test-123")
    assert rollback_info is not None
    
    # Rollback
    result = await executor.rollback(rollback_info)
    assert result.success is True
    assert result.status == ExecutionStatus.ROLLED_BACK


@pytest.mark.asyncio
async def test_airflow_executor_execute():
    """Test AirflowExecutor execution."""
    executor = AirflowExecutor()
    
    action = {
        "action_type": "airflow",
        "dag_id": "my_dag",
        "conf": {"key": "value"},
    }
    
    result = await executor.execute(action, {})
    
    assert result.success is True
    assert result.output["dag_id"] == "my_dag"


@pytest.mark.asyncio
async def test_k8s_executor_execute():
    """Test K8sExecutor execution."""
    executor = K8sExecutor()
    
    action = {
        "action_type": "kubernetes",
        "operation": "scale",
        "namespace": "default",
        "deployment": "my-app",
        "replicas": 3,
    }
    
    result = await executor.execute(action, {})
    
    assert result.success is True
    assert result.output["replicas"] == 3


@pytest.mark.asyncio
async def test_github_executor_execute():
    """Test GithubExecutor execution."""
    executor = GithubExecutor()
    
    action = {
        "action_type": "github",
        "operation": "create_issue",
        "repo": "owner/repo",
        "title": "Test issue",
    }
    
    result = await executor.execute(action, {})
    
    assert result.success is True
    assert "issue_number" in result.output


@pytest.mark.asyncio
async def test_sql_executor_execute():
    """Test SqlExecutor execution."""
    executor = SqlExecutor()
    
    action = {
        "action_type": "sql",
        "query": "SELECT * FROM users",
        "database": "mydb",
    }
    
    result = await executor.execute(action, {})
    
    assert result.success is True
    assert "rows_affected" in result.output


@pytest.mark.asyncio
async def test_cloud_api_executor_execute():
    """Test CloudApiExecutor execution."""
    executor = CloudApiExecutor()
    
    action = {
        "action_type": "cloud_api",
        "provider": "aws",
        "service": "ec2",
        "operation": "describe_instances",
    }
    
    result = await executor.execute(action, {})
    
    assert result.success is True
    assert result.output["provider"] == "aws"


def test_fabric_initialization():
    """Test ExecutionFabric initialization."""
    fabric = ExecutionFabric()
    
    executors = fabric.list_executors()
    executor_types = [e["executor_type"] for e in executors]
    
    assert "dbt" in executor_types
    assert "airflow" in executor_types
    assert "kubernetes" in executor_types
    assert "github" in executor_types
    assert "sql" in executor_types
    assert "cloud_api" in executor_types


def test_fabric_validate_action():
    """Test action validation."""
    fabric = ExecutionFabric()
    
    # Valid action
    action = {"action_type": "dbt", "command": "run"}
    validation = fabric.validate_action(action)
    assert validation["valid"] is True
    
    # Invalid executor type
    action = {"action_type": "invalid_type"}
    validation = fabric.validate_action(action)
    assert validation["valid"] is False


@pytest.mark.asyncio
async def test_fabric_execute():
    """Test fabric execution."""
    fabric = ExecutionFabric()
    
    action = {
        "action_type": "dbt",
        "command": "run",
        "models": "test_model",
    }
    
    result = await fabric.execute(action)
    
    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED


@pytest.mark.asyncio
async def test_fabric_rollback():
    """Test fabric rollback."""
    fabric = ExecutionFabric()
    
    action = {
        "execution_id": "test-rollback-123",
        "action_type": "dbt",
        "command": "run",
    }
    
    # Execute first
    await fabric.execute(action)
    
    # Rollback
    result = await fabric.rollback("test-rollback-123")
    assert result.success is True
    assert result.status == ExecutionStatus.ROLLED_BACK


def test_fabric_execution_log():
    """Test execution log."""
    fabric = ExecutionFabric()
    
    log = fabric.get_execution_log()
    assert isinstance(log, list)
    
    # Get stats
    stats = fabric.get_execution_stats()
    assert "total_executions" in stats
    assert "success_rate" in stats
