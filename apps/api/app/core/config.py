"""DataForge API — Core configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "DataForge"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+asyncpg://dataforge:dataforge@localhost:5432/dataforge"
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_database: str = "dataforge"
    groq_api_key: str = ""
    model_name: str = "llama-3.3-70b-versatile"

    class Config:
        env_file = ".env"


settings = Settings()
