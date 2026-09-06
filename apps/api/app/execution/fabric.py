"""Execution Fabric for managing and coordinating executors."""
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone

from .base import BaseExecutor, ExecutionResult, ExecutionStatus, RollbackInfo
from .executors import (
    DbtExecutor,
    AirflowExecutor,
    K8sExecutor,
    GithubExecutor,
    SqlExecutor,
    CloudApiExecutor,
)


class ExecutionFabric:
    """Central fabric for managing all executors."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.executors: Dict[str, BaseExecutor] = {}
        self.execution_log: List[Dict[str, Any]] = []
        self._initialize_executors()

    def _initialize_executors(self) -> None:
        """Initialize all available executors."""
        executor_classes = [
            DbtExecutor,
            AirflowExecutor,
            K8sExecutor,
            GithubExecutor,
            SqlExecutor,
            CloudApiExecutor,
        ]
        
        for executor_class in executor_classes:
            executor = executor_class(config=self.config)
            self.executors[executor.executor_type] = executor

    def get_executor(self, executor_type: str) -> Optional[BaseExecutor]:
        """Get an executor by type."""
        return self.executors.get(executor_type)

    def list_executors(self) -> List[Dict[str, Any]]:
        """List all available executors."""
        return [
            {
                "executor_type": executor.executor_type,
                "capabilities": executor.get_capabilities(),
                "execution_count": len(executor.execution_history),
            }
            for executor in self.executors.values()
        ]

    def validate_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Validate an action before execution."""
        executor_type = action.get("action_type", action.get("executor_type", ""))
        executor = self.executors.get(executor_type)
        
        if not executor:
            return {
                "valid": False,
                "error": f"Executor not found for type: {executor_type}",
            }
        
        is_valid = executor.validate_action(action)
        
        return {
            "valid": is_valid,
            "executor_type": executor_type,
            "capabilities": executor.get_capabilities() if is_valid else [],
        }

    # Bug #14 fix: Map action types to executor types
    ACTION_TO_EXECUTOR = {
        "rerun_pipeline": "dbt",
        "run_model": "dbt",
        "test_model": "dbt",
        "scale": "kubernetes",
        "restart": "kubernetes",
        "rollout": "kubernetes",
        "deploy": "kubernetes",
        "create_issue": "github",
        "create_pr": "github",
        "merge_pr": "github",
        "database": "sql",
        "query": "sql",
        "execute_sql": "sql",
        "dag_run": "airflow",
        "trigger_dag": "airflow",
        "cloud_api": "cloud_api",
        "aws": "cloud_api",
        "gcp": "cloud_api",
        "azure": "cloud_api",
    }

    async def execute(
        self,
        action: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Execute an action using the appropriate executor."""
        # Bug #14 fix: Map action_type to executor_type
        action_type = action.get("action_type", "")
        executor_type = action.get("executor_type", "")
        
        if not executor_type:
            executor_type = self.ACTION_TO_EXECUTOR.get(action_type, action_type)
        
        executor = self.executors.get(executor_type)
        
        if not executor:
            return ExecutionResult(
                execution_id=str(uuid4()),
                executor_type=executor_type,
                status=ExecutionStatus.FAILED,
                success=False,
                error=f"Executor not found for type: {executor_type}",
                start_time=datetime.now(timezone.utc),
            )
        
        # Validate action
        if not executor.validate_action(action):
            return ExecutionResult(
                execution_id=str(uuid4()),
                executor_type=executor_type,
                status=ExecutionStatus.FAILED,
                success=False,
                error="Action validation failed",
                start_time=datetime.now(timezone.utc),
            )
        
        # Execute
        result = await executor.execute(action, context or {})
        
        # Log execution
        self.execution_log.append({
            "execution_id": result.execution_id,
            "executor_type": executor_type,
            "action": action,
            "status": result.status,
            "success": result.success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        return result

    async def rollback(self, execution_id: str) -> ExecutionResult:
        """Rollback a previous execution."""
        # Find the executor and rollback info
        for executor in self.executors.values():
            rollback_info = executor.get_rollback_info(execution_id)
            if rollback_info:
                result = await executor.rollback(rollback_info)
                
                # Log rollback
                self.execution_log.append({
                    "execution_id": execution_id,
                    "executor_type": executor.executor_type,
                    "action": "rollback",
                    "status": result.status,
                    "success": result.success,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                
                return result
        
        return ExecutionResult(
            execution_id=execution_id,
            executor_type="unknown",
            status=ExecutionStatus.FAILED,
            success=False,
            error=f"No rollback info found for execution: {execution_id}",
            start_time=datetime.now(timezone.utc),
        )

    def get_execution_log(
        self,
        executor_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get execution log with optional filtering."""
        log = self.execution_log
        
        if executor_type:
            log = [entry for entry in log if entry["executor_type"] == executor_type]
        
        return log[-limit:]

    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        total_executions = len(self.execution_log)
        successful = sum(1 for e in self.execution_log if e["success"])
        failed = total_executions - successful
        
        return {
            "total_executions": total_executions,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total_executions if total_executions > 0 else 0,
            "executors_used": list(set(e["executor_type"] for e in self.execution_log)),
        }
