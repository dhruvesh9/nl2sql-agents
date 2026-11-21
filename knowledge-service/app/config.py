"""Settings for knowledge-service.

This module reads all settings from the .env file. No other module may hard-code a setting.
Pipeline step: infrastructure.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    knowledge_base_dir: str = "knowledge_base"
    # POST /generate reads the table catalog from db-service.
    db_service_url: str = "http://localhost:8001"
    # Long, because a schema with 1000 tables gives a big answer.
    db_service_timeout_seconds: float = 120
    log_level: str = "INFO"


settings = Settings()
