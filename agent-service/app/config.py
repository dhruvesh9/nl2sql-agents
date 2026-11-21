"""Settings for agent-service.

This module reads all settings from the .env file. No other module may hard-code a setting.
Pipeline step: infrastructure.
"""

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LlmParams(BaseModel):
    """LLM options for one agent. A value of None means: use the default (the LLM_* settings)."""

    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    reasoning_enabled: bool | None = None  # False = no thinking (faster). True = thinking.


class Settings(BaseSettings):
    # env_nested_delimiter lets one .env line set one option of one agent,
    # for example TABLE_CLASSIFIER__REASONING_ENABLED=true
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_nested_delimiter="__")

    together_api_key: str = ""
    llm_model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    llm_temperature: float = 0
    # None = send nothing. False = turn thinking off (faster). True = turn thinking on.
    llm_reasoning_enabled: bool | None = None
    # One block for each LLM agent. The field name is the agent name (the file name in app/agents/).
    # An option that you do not set uses the default above.
    query_analyzer: LlmParams = LlmParams()
    table_classifier: LlmParams = LlmParams()
    table_feedback: LlmParams = LlmParams()
    sql_generator: LlmParams = LlmParams()
    sql_validator: LlmParams = LlmParams()
    db_service_url: str = "http://localhost:8001"
    db_service_timeout_seconds: float = 30
    knowledge_service_url: str = "http://localhost:8002"
    knowledge_service_timeout_seconds: float = 10
    knowledge_cache_ttl_seconds: float = 300
    fk_depth: int = 1
    max_table_attempts: int = 3
    max_sql_attempts: int = 3
    pass_score: int = 80
    log_level: str = "INFO"
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"


settings = Settings()
