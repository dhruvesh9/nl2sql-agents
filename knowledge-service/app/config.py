"""Settings for knowledge-service.

This module reads all settings from the .env file. No other module may hard-code a setting.
Pipeline step: infrastructure.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_api_key: str
    knowledge_base_dir: str = "knowledge_base"
    log_level: str = "INFO"


settings = Settings()
