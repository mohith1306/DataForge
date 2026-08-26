from pydantic_settings import BaseSettings


class AgentConfig(BaseSettings):
    model_name: str = "llama-3.3-70b-versatile"
    temperature: float = 0.1
    max_tokens: int = 4096

    database_mcp_url: str = "http://localhost:8001"
    monitoring_mcp_url: str = "http://localhost:8002"
    github_mcp_url: str = "http://localhost:8003"
    remediation_mcp_url: str = "http://localhost:8004"

    model_config = {"env_prefix": "AGENT_"}


agent_config = AgentConfig()
