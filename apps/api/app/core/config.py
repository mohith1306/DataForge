"""DataForge API — Core configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "DataForge"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+asyncpg://dataforge:dataforge@localhost:5432/dataforge"

    # ClickHouse
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_database: str = "dataforge"

    # TrueForge
    trueforge_url: str = "http://localhost:8790"
    trueforge_enabled: bool = True

    # LLM
    groq_api_key: str = ""
    gemini_api_key: str = ""
    model_name: str = "google/gemini-3.6-flash"

    # GitHub
    github_repo: str = "mohith1306/DataForge"
    github_token: str = ""

    # Airflow (for pipeline rerun)
    airflow_url: str = "http://localhost:8080"
    airflow_username: str = "airflow"
    airflow_password: str = "airflow"

    # Kubernetes (for rollback)
    k8s_enabled: bool = False
    k8s_namespace: str = "dataforge"
    k8s_deployment: str = "dataforge-pipeline"

    # PagerDuty (for ticketing)
    pagerduty_enabled: bool = False
    pagerduty_routing_key: str = ""

    # Jira (for ticketing)
    jira_enabled: bool = False
    jira_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project: str = "DATA"

    # Gap 9: Demo mode — remediation targets controlled/test resources
    dataforge_env: str = "demo"  # "demo" or "production"

    # Monitor database backend (clickhouse | postgres | custom)
    monitor_db_type: str = "clickhouse"
    monitor_db_url: str = ""          # For postgres: postgres://user:pass@host/db
    monitor_db_schema: str = "public" # For postgres: schema name
    monitor_custom_query_url: str = ""  # For custom: HTTP query endpoint
    monitor_custom_auth_header: str = ""  # For custom: Authorization header
    monitor_queries_json: str = "{}"  # For custom: JSON mapping check_name → SQL

    class Config:
        env_file = ".env"


settings = Settings()
