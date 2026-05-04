from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"

    telegram_bot_token: str = Field(min_length=1)
    database_url: str = Field(min_length=1)
    github_token: str = Field(min_length=1)

    openai_api_key: str = Field(min_length=1)
    openai_model: str = "gpt-5.4-mini"
    openai_timeout_seconds: int = 30
    openai_prompt_version: str = "v1"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()


@lru_cache
def get_settings() -> Settings:
    return Settings()
