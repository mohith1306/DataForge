"""Base agent class for all specialized AI agents."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    """Message passed between agents."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    sender: str
    recipient: str
    content: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message_type: str = "info"


class AgentResult(BaseModel):
    """Result returned by an agent."""
    agent_id: str
    agent_type: str
    success: bool
    data: Dict[str, Any]
    recommendations: List[str] = []
    confidence: float = 0.0
    execution_time_ms: float = 0.0
    error: Optional[str] = None


class BaseAgent(ABC):
    """Base class for all specialized AI agents."""

    def __init__(self, agent_type: str, config: Optional[Dict[str, Any]] = None):
        self.agent_id = str(uuid4())
        self.agent_type = agent_type
        self.config = config or {}
        self.messages_received: List[AgentMessage] = []
        self.messages_sent: List[AgentMessage] = []

    @abstractmethod
    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """Process the given context and return a result."""
        pass

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent provides."""
        pass

    def receive_message(self, message: AgentMessage) -> None:
        """Receive a message from another agent."""
        self.messages_received.append(message)

    def send_message(self, recipient: str, content: Dict[str, Any], message_type: str = "info") -> AgentMessage:
        """Create a message to send to another agent."""
        message = AgentMessage(
            sender=self.agent_type,
            recipient=recipient,
            content=content,
            message_type=message_type,
        )
        self.messages_sent.append(message)
        return message

    def get_history(self) -> Dict[str, Any]:
        """Get agent's message history."""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "messages_received": len(self.messages_received),
            "messages_sent": len(self.messages_sent),
        }
