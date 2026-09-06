"""Base executor class for all execution types."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Status of an execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class ExecutionResult(BaseModel):
    """Result of an execution."""
    execution_id: str
    executor_type: str
    status: ExecutionStatus
    success: bool
    output: Dict[str, Any] = {}
    error: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0
    rollback_available: bool = True
    audit_trail: List[Dict[str, Any]] = []


class RollbackInfo(BaseModel):
    """Information needed for rollback."""
    execution_id: str
    executor_type: str
    rollback_data: Dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BaseExecutor(ABC):
    """Base class for all executors."""

    def __init__(self, executor_type: str, config: Optional[Dict[str, Any]] = None):
        self.executor_type = executor_type
        self.config = config or {}
        self.execution_history: List[ExecutionResult] = []
        self.rollback_stack: List[RollbackInfo] = []

    @abstractmethod
    async def execute(self, action: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        """Execute an action."""
        pass

    @abstractmethod
    async def rollback(self, rollback_info: RollbackInfo) -> ExecutionResult:
        """Rollback a previous execution."""
        pass

    @abstractmethod
    def validate_action(self, action: Dict[str, Any]) -> bool:
        """Validate that an action can be executed."""
        pass

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this executor provides."""
        pass

    def create_execution_result(
        self,
        execution_id: str,
        status: ExecutionStatus,
        success: bool,
        output: Dict[str, Any],
        error: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        rollback_available: bool = True,
    ) -> ExecutionResult:
        """Create an execution result."""
        if start_time is None:
            start_time = datetime.now(timezone.utc)
        if end_time is None:
            end_time = datetime.now(timezone.utc)
        
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        result = ExecutionResult(
            execution_id=execution_id,
            executor_type=self.executor_type,
            status=status,
            success=success,
            output=output,
            error=error,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            rollback_available=rollback_available,
        )
        
        self.execution_history.append(result)
        return result

    def add_rollback_info(self, rollback_info: RollbackInfo) -> None:
        """Add rollback information to the stack."""
        self.rollback_stack.append(rollback_info)

    def get_rollback_info(self, execution_id: str) -> Optional[RollbackInfo]:
        """Get rollback info for an execution."""
        for info in self.rollback_stack:
            if info.execution_id == execution_id:
                return info
        return None

    def get_execution_history(self) -> List[ExecutionResult]:
        """Get execution history."""
        return self.execution_history
