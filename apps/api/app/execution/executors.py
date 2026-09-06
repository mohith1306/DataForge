"""Specialized executors for different action types."""
from typing import Any, Dict, List
from uuid import uuid4
from datetime import datetime, timezone
import asyncio
import random

from .base import BaseExecutor, ExecutionResult, ExecutionStatus, RollbackInfo


class DbtExecutor(BaseExecutor):
    """Executor for dbt model runs and transformations."""

    def __init__(self, config=None):
        super().__init__("dbt", config)

    async def execute(self, action: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        """Execute a dbt command."""
        execution_id = action.get("execution_id", str(uuid4()))
        start_time = datetime.now(timezone.utc)
        
        command = action.get("command", "run")
        models = action.get("models", "")
        full_refresh = action.get("full_refresh", False)
        
        # Simulate dbt execution
        await asyncio.sleep(0.1)
        
        # Store rollback info
        rollback_data = {
            "command": command,
            "models": models,
            "previous_state": context.get("previous_state", {}),
        }
        self.add_rollback_info(RollbackInfo(
            execution_id=execution_id,
            executor_type=self.executor_type,
            rollback_data=rollback_data,
        ))
        
        output = {
            "command": f"dbt {command}",
            "models": models,
            "full_refresh": full_refresh,
            "rows_affected": random.randint(100, 10000),
            "execution_time": "2.5s",
        }
        
        return self.create_execution_result(
            execution_id=execution_id,
            status=ExecutionStatus.COMPLETED,
            success=True,
            output=output,
            start_time=start_time,
        )

    async def rollback(self, rollback_info: RollbackInfo) -> ExecutionResult:
        """Rollback a dbt execution."""
        start_time = datetime.now(timezone.utc)
        
        # Simulate rollback
        await asyncio.sleep(0.05)
        
        output = {
            "rollback_command": "dbt run --models ...",
            "status": "rolled_back",
        }
        
        return self.create_execution_result(
            execution_id=rollback_info.execution_id,
            status=ExecutionStatus.ROLLED_BACK,
            success=True,
            output=output,
            start_time=start_time,
            rollback_available=False,
        )

    def validate_action(self, action: Dict[str, Any]) -> bool:
        """Validate dbt action."""
        valid_commands = ["run", "test", "build", "seed", "snapshot"]
        return action.get("command", "run") in valid_commands

    def get_capabilities(self) -> List[str]:
        return ["model_run", "model_test", "model_build", "seed", "snapshot"]


class AirflowExecutor(BaseExecutor):
    """Executor for Airflow DAG runs."""

    def __init__(self, config=None):
        super().__init__("airflow", config)

    async def execute(self, action: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        """Execute an Airflow DAG run."""
        execution_id = action.get("execution_id", str(uuid4()))
        start_time = datetime.now(timezone.utc)
        
        dag_id = action.get("dag_id", "")
        conf = action.get("conf", {})
        
        # Simulate Airflow execution
        await asyncio.sleep(0.1)
        
        rollback_data = {
            "dag_id": dag_id,
            "run_id": f"manual__{datetime.now(timezone.utc).isoformat()}",
        }
        self.add_rollback_info(RollbackInfo(
            execution_id=execution_id,
            executor_type=self.executor_type,
            rollback_data=rollback_data,
        ))
        
        output = {
            "dag_id": dag_id,
            "run_id": rollback_data["run_id"],
            "state": "success",
            "tasks_completed": random.randint(5, 20),
        }
        
        return self.create_execution_result(
            execution_id=execution_id,
            status=ExecutionStatus.COMPLETED,
            success=True,
            output=output,
            start_time=start_time,
        )

    async def rollback(self, rollback_info: RollbackInfo) -> ExecutionResult:
        """Rollback an Airflow DAG run."""
        start_time = datetime.now(timezone.utc)
        
        await asyncio.sleep(0.05)
        
        output = {
            "dag_id": rollback_info.rollback_data.get("dag_id"),
            "action": "dag_run_stopped",
        }
        
        return self.create_execution_result(
            execution_id=rollback_info.execution_id,
            status=ExecutionStatus.ROLLED_BACK,
            success=True,
            output=output,
            start_time=start_time,
            rollback_available=False,
        )

    def validate_action(self, action: Dict[str, Any]) -> bool:
        """Validate Airflow action."""
        return bool(action.get("dag_id"))

    def get_capabilities(self) -> List[str]:
        return ["dag_run", "dag_stop", "task_trigger"]


class K8sExecutor(BaseExecutor):
    """Executor for Kubernetes operations."""

    def __init__(self, config=None):
        super().__init__("kubernetes", config)

    async def execute(self, action: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        """Execute a Kubernetes operation."""
        execution_id = action.get("execution_id", str(uuid4()))
        start_time = datetime.now(timezone.utc)
        
        operation = action.get("operation", "scale")
        namespace = action.get("namespace", "default")
        deployment = action.get("deployment", "")
        replicas = action.get("replicas", 1)
        
        await asyncio.sleep(0.1)
        
        rollback_data = {
            "operation": operation,
            "namespace": namespace,
            "deployment": deployment,
            "previous_replicas": context.get("current_replicas", 1),
        }
        self.add_rollback_info(RollbackInfo(
            execution_id=execution_id,
            executor_type=self.executor_type,
            rollback_data=rollback_data,
        ))
        
        output = {
            "operation": operation,
            "namespace": namespace,
            "deployment": deployment,
            "replicas": replicas,
            "status": "success",
        }
        
        return self.create_execution_result(
            execution_id=execution_id,
            status=ExecutionStatus.COMPLETED,
            success=True,
            output=output,
            start_time=start_time,
        )

    async def rollback(self, rollback_info: RollbackInfo) -> ExecutionResult:
        """Rollback a Kubernetes operation."""
        start_time = datetime.now(timezone.utc)
        
        await asyncio.sleep(0.05)
        
        output = {
            "operation": "scale",
            "deployment": rollback_info.rollback_data.get("deployment"),
            "replicas": rollback_info.rollback_data.get("previous_replicas"),
            "status": "rolled_back",
        }
        
        return self.create_execution_result(
            execution_id=rollback_info.execution_id,
            status=ExecutionStatus.ROLLED_BACK,
            success=True,
            output=output,
            start_time=start_time,
            rollback_available=False,
        )

    def validate_action(self, action: Dict[str, Any]) -> bool:
        """Validate Kubernetes action."""
        valid_operations = ["scale", "restart", "rollout", "delete"]
        return action.get("operation", "scale") in valid_operations

    def get_capabilities(self) -> List[str]:
        return ["scale", "restart", "rollout", "delete", "status"]


class GithubExecutor(BaseExecutor):
    """Executor for GitHub operations (PR, issues, actions)."""

    def __init__(self, config=None):
        super().__init__("github", config)

    async def execute(self, action: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        """Execute a GitHub operation."""
        execution_id = action.get("execution_id", str(uuid4()))
        start_time = datetime.now(timezone.utc)
        
        operation = action.get("operation", "create_issue")
        repo = action.get("repo", "")
        
        await asyncio.sleep(0.1)
        
        rollback_data = {
            "operation": operation,
            "repo": repo,
            "issue_number": random.randint(100, 999),
        }
        self.add_rollback_info(RollbackInfo(
            execution_id=execution_id,
            executor_type=self.executor_type,
            rollback_data=rollback_data,
        ))
        
        output = {
            "operation": operation,
            "repo": repo,
            "issue_number": rollback_data["issue_number"],
            "status": "created",
        }
        
        return self.create_execution_result(
            execution_id=execution_id,
            status=ExecutionStatus.COMPLETED,
            success=True,
            output=output,
            start_time=start_time,
        )

    async def rollback(self, rollback_info: RollbackInfo) -> ExecutionResult:
        """Rollback a GitHub operation."""
        start_time = datetime.now(timezone.utc)
        
        await asyncio.sleep(0.05)
        
        output = {
            "operation": "close_issue",
            "issue_number": rollback_info.rollback_data.get("issue_number"),
            "status": "closed",
        }
        
        return self.create_execution_result(
            execution_id=rollback_info.execution_id,
            status=ExecutionStatus.ROLLED_BACK,
            success=True,
            output=output,
            start_time=start_time,
            rollback_available=False,
        )

    def validate_action(self, action: Dict[str, Any]) -> bool:
        """Validate GitHub action."""
        valid_operations = ["create_issue", "create_pr", "merge_pr", "close_issue"]
        return action.get("operation", "create_issue") in valid_operations

    def get_capabilities(self) -> List[str]:
        return ["create_issue", "create_pr", "merge_pr", "close_issue"]


class SqlExecutor(BaseExecutor):
    """Executor for SQL operations."""

    def __init__(self, config=None):
        super().__init__("sql", config)

    async def execute(self, action: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        """Execute a SQL operation."""
        execution_id = action.get("execution_id", str(uuid4()))
        start_time = datetime.now(timezone.utc)
        
        query = action.get("query", "")
        database = action.get("database", "")
        
        await asyncio.sleep(0.1)
        
        rollback_data = {
            "query": query,
            "database": database,
            "backup_table": f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        }
        self.add_rollback_info(RollbackInfo(
            execution_id=execution_id,
            executor_type=self.executor_type,
            rollback_data=rollback_data,
        ))
        
        output = {
            "query": query[:100] + "..." if len(query) > 100 else query,
            "database": database,
            "rows_affected": random.randint(0, 1000),
            "execution_time": "0.5s",
        }
        
        return self.create_execution_result(
            execution_id=execution_id,
            status=ExecutionStatus.COMPLETED,
            success=True,
            output=output,
            start_time=start_time,
        )

    async def rollback(self, rollback_info: RollbackInfo) -> ExecutionResult:
        """Rollback a SQL operation."""
        start_time = datetime.now(timezone.utc)
        
        await asyncio.sleep(0.05)
        
        output = {
            "rollback_query": f"RESTORE FROM {rollback_info.rollback_data.get('backup_table')}",
            "status": "restored",
        }
        
        return self.create_execution_result(
            execution_id=rollback_info.execution_id,
            status=ExecutionStatus.ROLLED_BACK,
            success=True,
            output=output,
            start_time=start_time,
            rollback_available=False,
        )

    def validate_action(self, action: Dict[str, Any]) -> bool:
        """Validate SQL action."""
        return bool(action.get("query"))

    def get_capabilities(self) -> List[str]:
        return ["select", "insert", "update", "delete", "ddl"]


class CloudApiExecutor(BaseExecutor):
    """Executor for cloud API operations (AWS, GCP, Azure)."""

    def __init__(self, config=None):
        super().__init__("cloud_api", config)

    async def execute(self, action: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        """Execute a cloud API operation."""
        execution_id = action.get("execution_id", str(uuid4()))
        start_time = datetime.now(timezone.utc)
        
        provider = action.get("provider", "aws")
        service = action.get("service", "")
        operation = action.get("operation", "")
        
        await asyncio.sleep(0.1)
        
        rollback_data = {
            "provider": provider,
            "service": service,
            "operation": operation,
            "resource_id": f"resource-{uuid4().hex[:8]}",
        }
        self.add_rollback_info(RollbackInfo(
            execution_id=execution_id,
            executor_type=self.executor_type,
            rollback_data=rollback_data,
        ))
        
        output = {
            "provider": provider,
            "service": service,
            "operation": operation,
            "resource_id": rollback_data["resource_id"],
            "status": "success",
        }
        
        return self.create_execution_result(
            execution_id=execution_id,
            status=ExecutionStatus.COMPLETED,
            success=True,
            output=output,
            start_time=start_time,
        )

    async def rollback(self, rollback_info: RollbackInfo) -> ExecutionResult:
        """Rollback a cloud API operation."""
        start_time = datetime.now(timezone.utc)
        
        await asyncio.sleep(0.05)
        
        output = {
            "provider": rollback_info.rollback_data.get("provider"),
            "resource_id": rollback_info.rollback_data.get("resource_id"),
            "action": "deleted",
            "status": "rolled_back",
        }
        
        return self.create_execution_result(
            execution_id=rollback_info.execution_id,
            status=ExecutionStatus.ROLLED_BACK,
            success=True,
            output=output,
            start_time=start_time,
            rollback_available=False,
        )

    def validate_action(self, action: Dict[str, Any]) -> bool:
        """Validate cloud API action."""
        return bool(action.get("provider") and action.get("service"))

    def get_capabilities(self) -> List[str]:
        return ["ec2", "s3", "rds", "lambda", "gke", "cloud_run", "aks"]
