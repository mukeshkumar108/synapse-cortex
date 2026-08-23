import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8010
    ENV: str = "development"
    
    # Database Configuration (SQLite fallback for tests/local, Async Postgres for prod)
    DATABASE_URL: str = "sqlite+aiosqlite:///./synapse_cortex.db"
    
    # Honcho Integration
    HONCHO_BASE_URL: str = "http://localhost:8000"
    HONCHO_API_KEY: str = "mock-api-key"
    HONCHO_CONTEXT_ENABLED: bool = True
    HONCHO_TIMEOUT_SECONDS: float = 3.0
    HONCHO_CONTEXT_BUDGET_SECONDS: float = 4.0
    SYNAPSE_CORTEX_API_TOKEN: str = ""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
