"""Settings for db-service.

This module reads all settings from the .env file. No other module may hard-code a setting.
Pipeline step: infrastructure.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    statement_timeout_ms: int = 5000
    default_max_rows: int = 100
    max_rows_limit: int = 1000
    max_fk_depth: int = 3
    log_level: str = "INFO"


settings = Settings()
