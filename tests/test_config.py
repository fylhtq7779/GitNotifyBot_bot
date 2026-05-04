from app.config import Settings


def test_settings_reads_required_values() -> None:
    settings = Settings(
        telegram_bot_token="telegram-token",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        github_token="github-token",
        openai_api_key="openai-key",
    )

    assert settings.telegram_bot_token == "telegram-token"
    assert settings.openai_model == "gpt-5.4-mini"
    assert settings.openai_timeout_seconds == 30
    assert settings.openai_prompt_version == "v1"


def test_log_level_is_uppercase() -> None:
    settings = Settings(
        log_level="debug",
        telegram_bot_token="telegram-token",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        github_token="github-token",
        openai_api_key="openai-key",
    )

    assert settings.log_level == "DEBUG"
