from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class UnderstandingAgentSettings(BaseSettings):
    MAX_USER_TURNS: int = 8
    ANONYMITY_INFERENCE_THRESHOLD: int = 6
    CONTEXT_WINDOW_SIZE: int = 20
    LLM_TEMPERATURE: float = 0.0
    LLM_MODEL_NAME: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(
        env_prefix="UA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = UnderstandingAgentSettings()
