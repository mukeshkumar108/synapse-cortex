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
    HONCHO_HEART_SOCIAL_ENABLED: bool = True      # the Heart's feed of Honcho's inference (a labelled hypothesis, never world truth); switch off to stop the dialectic calls
    HONCHO_TIMEOUT_SECONDS: float = 3.0
    HONCHO_CONTEXT_BUDGET_SECONDS: float = 4.0
    SYNAPSE_CORTEX_API_TOKEN: str = ""
    # Per-product credentials, e.g. "bloom=<token>,sophie=<token>". A product token fixes the caller's product,
    # limits it to the product routes, and cannot be used to claim another product. Empty = legacy token only.
    SYNAPSE_PRODUCT_TOKENS: str = ""
    # Connected understanding (entities, situations, links, world views). OFF by default: it writes new kinds of personal
    # data, so enabling it for real users is an explicit review decision (docs/IMPLEMENTATION_STATUS.md).
    CONNECTED_WORLD_ENABLED: bool = False
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
