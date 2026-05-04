# GitNotifyBot Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working foundation for GitNotifyBot: project tooling, configuration, database schema, domain helpers, prompt YAML loading, OpenAI summary adapter, and runnable bot/worker entrypoint stubs.

**Architecture:** This implements the shared modular-monolith base from the approved design spec. It creates focused modules for domain rules, storage, integrations, config, logging, prompts, and runtime entrypoints, while leaving full Telegram UX and worker scheduling for follow-up plans.

**Tech Stack:** Python 3.12, uv, aiogram 3, SQLAlchemy 2 async, Alembic, PostgreSQL, Pydantic Settings, httpx, OpenAI Python SDK, PyYAML, pytest, pytest-asyncio, Ruff.

---

## Scope

This plan intentionally covers only the foundation slice. It does not implement the full add-subscription wizard, background GitHub checking loop, notification fanout, or real Telegram handlers beyond health/start stubs. Those will be implemented in later plans after this base is tested and committed.

Implemented here:

- Python project setup.
- App package layout.
- Settings and structured logging.
- Domain enums and GitHub source key helper.
- SQLAlchemy models matching the approved spec.
- Alembic initial migration.
- Prompt YAML template and loader.
- OpenAI Responses API adapter with structured summary parsing.
- Minimal bot and worker entrypoints.
- Docker Compose and env example.
- Focused tests for foundation behavior.

## File Map

- Create `pyproject.toml`: Python dependencies, scripts, pytest and Ruff config.
- Create `.env.example`: documented environment variables.
- Modify `README.md`: foundation-level local development guide.
- Create `app/__init__.py`: package marker.
- Create `app/config.py`: Pydantic Settings.
- Create `app/logging.py`: JSON-ish structured logging setup.
- Create `app/domain/enums.py`: shared enum values.
- Create `app/domain/github.py`: GitHub repo parsing and source key builder.
- Create `app/storage/base.py`: SQLAlchemy Declarative Base.
- Create `app/storage/models.py`: database ORM models.
- Create `app/storage/session.py`: async engine/session factory.
- Create `alembic.ini`: Alembic config.
- Create `app/storage/migrations/env.py`: Alembic async migration environment.
- Create `app/storage/migrations/script.py.mako`: migration template.
- Create `app/storage/migrations/versions/0001_initial_schema.py`: initial schema.
- Create `app/prompts/github_update_summary.v1.yaml`: versioned prompt template.
- Create `app/integrations/llm/schemas.py`: summary dataclasses/Pydantic models.
- Create `app/integrations/llm/prompt_loader.py`: YAML prompt loading/rendering.
- Create `app/integrations/llm/openai_client.py`: OpenAI adapter.
- Create `app/bot/__main__.py`: minimal bot process entrypoint.
- Create `app/worker/__main__.py`: minimal worker process entrypoint.
- Create `tests/test_github_domain.py`: domain helper tests.
- Create `tests/test_prompt_loader.py`: prompt loader tests.
- Create `tests/test_openai_client.py`: OpenAI adapter tests with fake client.
- Create `docker-compose.yml`: bot, worker, postgres services.

## Task 1: Project Tooling

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Create project configuration**

Create `pyproject.toml`:

```toml
[project]
name = "gitnotifybot-bot"
version = "0.1.0"
description = "Telegram bot for GitHub repository update notifications with LLM summaries."
requires-python = ">=3.12"
dependencies = [
    "aiogram>=3.13.1",
    "alembic>=1.13.3",
    "asyncpg>=0.29.0",
    "httpx>=0.27.2",
    "openai>=1.52.0",
    "pydantic>=2.9.2",
    "pydantic-settings>=2.6.0",
    "pyyaml>=6.0.2",
    "sqlalchemy>=2.0.35",
]

[dependency-groups]
dev = [
    "pytest>=8.3.3",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.7.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 2: Create environment example**

Create `.env.example`:

```dotenv
APP_ENV=local
LOG_LEVEL=INFO

TELEGRAM_BOT_TOKEN=replace-me
DATABASE_URL=postgresql+asyncpg://gitnotifybot:gitnotifybot@localhost:5432/gitnotifybot

GITHUB_TOKEN=replace-me

OPENAI_API_KEY=replace-me
OPENAI_MODEL=gpt-5.4-mini
OPENAI_TIMEOUT_SECONDS=30
OPENAI_PROMPT_VERSION=v1
```

- [ ] **Step 3: Update README with local commands**

Replace `README.md` with:

```markdown
# GitNotifyBot_bot

Telegram bot for tracking public GitHub repository updates and sending concise LLM-generated summaries.

## Architecture

The app is a modular monolith with two runtime processes:

- `bot`: Telegram UI, commands, buttons, and settings flows.
- `worker`: scheduled GitHub checks, LLM summaries, and notifications.

Both processes share PostgreSQL.

## Local Development

Install dependencies:

```bash
uv sync
```

Copy environment:

```bash
cp .env.example .env
```

Run tests:

```bash
uv run pytest
```

Run lint:

```bash
uv run ruff check .
```

Start local services:

```bash
docker compose up postgres
```

Run migrations:

```bash
uv run alembic upgrade head
```

Run bot process:

```bash
uv run python -m app.bot
```

Run worker process:

```bash
uv run python -m app.worker
```
```

- [ ] **Step 4: Verify tooling metadata**

Run:

```bash
uv lock
```

Expected: command exits 0 and creates `uv.lock`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .env.example README.md
git commit -m "chore: scaffold python project tooling"
```

## Task 2: Config And Logging

**Files:**
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/logging.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Create failing config tests**

Create `tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL because `app.config` does not exist.

- [ ] **Step 3: Create package and settings**

Create `app/__init__.py`:

```python
"""GitNotifyBot application package."""
```

Create `app/config.py`:

```python
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
```

- [ ] **Step 4: Create logging setup**

Create `app/logging.py`:

```python
import logging
import sys


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,
    )
```

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/__init__.py app/config.py app/logging.py tests/test_config.py
git commit -m "feat: add application settings"
```

## Task 3: Domain Helpers

**Files:**
- Create: `app/domain/__init__.py`
- Create: `app/domain/enums.py`
- Create: `app/domain/github.py`
- Create: `tests/test_github_domain.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_github_domain.py`:

```python
import pytest

from app.domain.enums import GitHubSourceType
from app.domain.github import GitHubRepositoryRef, build_source_key, parse_github_repository


@pytest.mark.parametrize(
    ("raw", "owner", "repo"),
    [
        ("anthropics/claude-code", "anthropics", "claude-code"),
        ("https://github.com/anthropics/claude-code", "anthropics", "claude-code"),
        ("https://github.com/anthropics/claude-code.git", "anthropics", "claude-code"),
    ],
)
def test_parse_github_repository(raw: str, owner: str, repo: str) -> None:
    parsed = parse_github_repository(raw)

    assert parsed == GitHubRepositoryRef(owner=owner, name=repo)
    assert parsed.full_name == f"{owner}/{repo}"


def test_parse_github_repository_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="GitHub repository"):
        parse_github_repository("not a repo")


def test_build_release_source_key() -> None:
    assert (
        build_source_key(GitHubSourceType.RELEASES, "Anthropics", "Claude-Code")
        == "github:releases:anthropics/claude-code"
    )


def test_build_file_source_key() -> None:
    assert (
        build_source_key(
            GitHubSourceType.FILE,
            "Anthropics",
            "Claude-Code",
            branch="Main",
            file_path="/CHANGELOG.md",
        )
        == "github:file:anthropics/claude-code:Main:CHANGELOG.md"
    )
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_github_domain.py -v
```

Expected: FAIL because domain modules do not exist.

- [ ] **Step 3: Add enums**

Create `app/domain/__init__.py`:

```python
"""Domain helpers and value objects."""
```

Create `app/domain/enums.py`:

```python
from enum import StrEnum


class ChatType(StrEnum):
    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"


class GitHubSourceType(StrEnum):
    RELEASES = "releases"
    FILE = "file"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


class UpdateType(StrEnum):
    RELEASE = "release"
    FILE_CHANGE = "file_change"


class SummaryStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class NotificationStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
```

- [ ] **Step 4: Add GitHub helpers**

Create `app/domain/github.py`:

```python
from dataclasses import dataclass
from urllib.parse import urlparse

from app.domain.enums import GitHubSourceType


@dataclass(frozen=True)
class GitHubRepositoryRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


def parse_github_repository(raw: str) -> GitHubRepositoryRef:
    value = raw.strip()
    if value.startswith("https://") or value.startswith("http://"):
        parsed = urlparse(value)
        if parsed.netloc.lower() != "github.com":
            raise ValueError("Expected a GitHub repository URL or owner/repo value")
        parts = [part for part in parsed.path.strip("/").split("/") if part]
    else:
        parts = [part for part in value.strip("/").split("/") if part]

    if len(parts) < 2:
        raise ValueError("Expected a GitHub repository URL or owner/repo value")

    owner = parts[0].strip()
    name = parts[1].removesuffix(".git").strip()
    if not owner or not name:
        raise ValueError("Expected a GitHub repository URL or owner/repo value")

    return GitHubRepositoryRef(owner=owner, name=name)


def build_source_key(
    source_type: GitHubSourceType,
    owner: str,
    repo: str,
    *,
    branch: str | None = None,
    file_path: str | None = None,
) -> str:
    normalized_repo = f"{owner.lower()}/{repo.lower()}"
    if source_type == GitHubSourceType.RELEASES:
        return f"github:releases:{normalized_repo}"

    if source_type == GitHubSourceType.FILE:
        if not branch or not file_path:
            raise ValueError("File source key requires branch and file_path")
        normalized_path = file_path.strip("/")
        return f"github:file:{normalized_repo}:{branch}:{normalized_path}"

    raise ValueError(f"Unsupported GitHub source type: {source_type}")
```

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_github_domain.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/domain tests/test_github_domain.py
git commit -m "feat: add github domain helpers"
```

## Task 4: Storage Models

**Files:**
- Create: `app/storage/__init__.py`
- Create: `app/storage/base.py`
- Create: `app/storage/models.py`
- Create: `app/storage/session.py`
- Create: `tests/test_storage_models.py`

- [ ] **Step 1: Write failing model metadata test**

Create `tests/test_storage_models.py`:

```python
from app.storage.base import Base


def test_initial_schema_tables_are_registered() -> None:
    expected = {
        "users",
        "chats",
        "chat_members",
        "repositories",
        "github_sources",
        "subscriptions",
        "subscription_state",
        "updates",
        "llm_summaries",
        "notifications",
    }

    assert expected.issubset(Base.metadata.tables.keys())
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_storage_models.py -v
```

Expected: FAIL because storage modules do not exist.

- [ ] **Step 3: Add SQLAlchemy base**

Create `app/storage/__init__.py`:

```python
"""Persistence layer."""
```

Create `app/storage/base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 4: Add ORM models**

Create `app/storage/models.py` with the models from the approved spec. Use SQLAlchemy 2 `Mapped` annotations, server defaults for timestamps, enum string columns, and uniqueness constraints:

```python
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.storage.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(16))


class Chat(TimestampMixin, Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    summary_language: Mapped[str] = mapped_column(String(16), default="ru", server_default="ru")
    summary_style: Mapped[str] = mapped_column(
        String(64),
        default="short_technical",
        server_default="short_technical",
    )
    summary_preferences: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ChatMember(Base):
    __tablename__ = "chat_members"
    __table_args__ = (UniqueConstraint("chat_id", "user_id", name="uq_chat_members_chat_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Repository(TimestampMixin, Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("owner", "name", name="uq_repositories_owner_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    full_name: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    html_url: Mapped[str] = mapped_column(String(1024))
    default_branch: Mapped[str] = mapped_column(String(255))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GitHubSource(TimestampMixin, Base):
    __tablename__ = "github_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_key: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    branch: Mapped[str | None] = mapped_column(String(255))
    file_path: Mapped[str | None] = mapped_column(String(1024))
    etag: Mapped[str | None] = mapped_column(String(512))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    rate_limited_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("chat_id", "github_source_id", name="uq_subscriptions_chat_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    github_source_id: Mapped[int] = mapped_column(ForeignKey("github_sources.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", server_default="active")
    check_interval_minutes: Mapped[int] = mapped_column(Integer)
    next_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class SubscriptionState(Base):
    __tablename__ = "subscription_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        unique=True,
    )
    last_seen_release_id: Mapped[str | None] = mapped_column(String(255))
    last_seen_tag: Mapped[str | None] = mapped_column(String(255))
    last_seen_file_sha: Mapped[str | None] = mapped_column(String(255))
    last_seen_commit_sha: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Update(Base):
    __tablename__ = "updates"
    __table_args__ = (UniqueConstraint("github_source_id", "external_id", name="uq_updates_source_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    github_source_id: Mapped[int] = mapped_column(ForeignKey("github_sources.id", ondelete="CASCADE"))
    update_type: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(512))
    title: Mapped[str | None] = mapped_column(String(1024))
    url: Mapped[str | None] = mapped_column(String(2048))
    from_sha: Mapped[str | None] = mapped_column(String(255))
    to_sha: Mapped[str | None] = mapped_column(String(255))
    release_tag: Mapped[str | None] = mapped_column(String(255))
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LLMSummary(Base):
    __tablename__ = "llm_summaries"
    __table_args__ = (
        UniqueConstraint(
            "update_id",
            "language",
            "style",
            "preferences_hash",
            "prompt_version",
            name="uq_llm_summaries_cache_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    update_id: Mapped[int] = mapped_column(ForeignKey("updates.id", ondelete="CASCADE"))
    language: Mapped[str] = mapped_column(String(16))
    style: Mapped[str] = mapped_column(String(64))
    preferences_hash: Mapped[str] = mapped_column(String(64))
    prompt_id: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(255))
    reasoning_effort: Mapped[str] = mapped_column(String(32))
    text_verbosity: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    summary_text: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("chat_id", "update_id", name="uq_notifications_chat_update"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"))
    update_id: Mapped[int] = mapped_column(ForeignKey("updates.id", ondelete="CASCADE"))
    llm_summary_id: Mapped[int | None] = mapped_column(ForeignKey("llm_summaries.id"))
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 5: Import models in base module**

Append to `app/storage/base.py`:

```python
# Import models so Base.metadata is populated for Alembic and tests.
from app.storage import models  # noqa: E402,F401
```

- [ ] **Step 6: Add session factory**

Create `app/storage/session.py`:

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings


def create_session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        async with session.begin():
            yield session
```

- [ ] **Step 7: Run model test**

Run:

```bash
uv run pytest tests/test_storage_models.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/storage tests/test_storage_models.py
git commit -m "feat: add database models"
```

## Task 5: Alembic Initial Migration

**Files:**
- Create: `alembic.ini`
- Create: `app/storage/migrations/env.py`
- Create: `app/storage/migrations/script.py.mako`
- Create: `app/storage/migrations/versions/0001_initial_schema.py`

- [ ] **Step 1: Create Alembic config**

Create `alembic.ini`:

```ini
[alembic]
script_location = app/storage/migrations
prepend_sys_path = .
sqlalchemy.url = postgresql+asyncpg://gitnotifybot:gitnotifybot@localhost:5432/gitnotifybot

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Create Alembic env**

Create `app/storage/migrations/env.py`:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.storage.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Create migration template**

Create `app/storage/migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Generate initial migration**

Run:

```bash
uv run alembic revision --autogenerate -m "initial schema"
```

Expected: command creates one file under `app/storage/migrations/versions/` containing `op.create_table` calls for the ten ORM tables.

- [ ] **Step 5: Rename migration file**

Rename the generated file to:

```text
app/storage/migrations/versions/0001_initial_schema.py
```

After renaming, open the file and confirm `upgrade()` contains `op.create_table` calls for these table names:

```text
users
chats
chat_members
repositories
github_sources
subscriptions
subscription_state
updates
llm_summaries
notifications
```

Also confirm `downgrade()` drops the same tables in dependency-safe reverse order.

- [ ] **Step 6: Verify migration applies**

Run:

```bash
docker compose up -d postgres
uv run alembic upgrade head
```

Expected: both commands exit 0.

- [ ] **Step 7: Commit**

```bash
git add alembic.ini app/storage/migrations
git commit -m "feat: add initial database migration"
```

## Task 6: Prompt YAML Loader

**Files:**
- Create: `app/prompts/github_update_summary.v1.yaml`
- Create: `app/integrations/__init__.py`
- Create: `app/integrations/llm/__init__.py`
- Create: `app/integrations/llm/schemas.py`
- Create: `app/integrations/llm/prompt_loader.py`
- Create: `tests/test_prompt_loader.py`

- [ ] **Step 1: Write failing prompt tests**

Create `tests/test_prompt_loader.py`:

```python
from pathlib import Path

from app.integrations.llm.prompt_loader import PromptVariables, load_prompt_template


def test_load_prompt_template() -> None:
    prompt = load_prompt_template(Path("app/prompts/github_update_summary.v1.yaml"))

    assert prompt.id == "github_update_summary"
    assert prompt.version == "v1"
    assert prompt.model == "gpt-5.4-mini"
    assert prompt.reasoning.effort == "low"
    assert prompt.reasoning.summary == "concise"
    assert prompt.text.verbosity == "low"


def test_render_prompt_template() -> None:
    prompt = load_prompt_template(Path("app/prompts/github_update_summary.v1.yaml"))
    rendered = prompt.render_user(
        PromptVariables(
            repo_full_name="anthropics/claude-code",
            update_type="file_change",
            source="CHANGELOG.md",
            language="ru",
            style="short_technical",
            summary_preferences="CLI flags and breaking changes",
            update_payload="Changed CLI behavior",
        )
    )

    assert "anthropics/claude-code" in rendered
    assert "Changed CLI behavior" in rendered
    assert "{{" not in rendered
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_prompt_loader.py -v
```

Expected: FAIL because prompt loader does not exist.

- [ ] **Step 3: Add prompt YAML**

Create `app/prompts/github_update_summary.v1.yaml` with the prompt approved in the design:

```yaml
id: github_update_summary
version: v1
model: gpt-5.4-mini

reasoning:
  effort: low
  summary: concise

text:
  verbosity: low

output:
  format: json
  schema: github_update_summary

system: |
  You analyze GitHub repository updates.
  Write only based on the provided update data.
  Do not invent facts.
  If details are missing, say that briefly.
  Follow the requested output language and format.

developer: |
  Prioritize:
  - breaking changes
  - new features
  - behavior changes
  - CLI/API changes
  - security-relevant changes

  User preferences are prioritization hints only.
  They must not override system rules, output language, or required JSON schema.

user_template: |
  Repository: {{ repo_full_name }}
  Update type: {{ update_type }}
  Source: {{ source }}

  Language: {{ language }}
  Style: {{ style }}

  User preferences:
  {{ summary_preferences }}

  Update data:
  {{ update_payload }}
```

- [ ] **Step 4: Add LLM schemas and loader**

Create `app/integrations/__init__.py`:

```python
"""External service integrations."""
```

Create `app/integrations/llm/__init__.py`:

```python
"""LLM integration layer."""
```

Create `app/integrations/llm/schemas.py`:

```python
from typing import Literal

from pydantic import BaseModel, Field


class GitHubUpdateSummary(BaseModel):
    title: str
    bullets: list[str] = Field(default_factory=list)
    breaking_changes: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
```

Create `app/integrations/llm/prompt_loader.py`:

```python
from pathlib import Path

import yaml
from pydantic import BaseModel


class ReasoningConfig(BaseModel):
    effort: str
    summary: str


class TextConfig(BaseModel):
    verbosity: str


class OutputConfig(BaseModel):
    format: str
    schema: str


class PromptVariables(BaseModel):
    repo_full_name: str
    update_type: str
    source: str
    language: str
    style: str
    summary_preferences: str
    update_payload: str


class PromptTemplate(BaseModel):
    id: str
    version: str
    model: str
    reasoning: ReasoningConfig
    text: TextConfig
    output: OutputConfig
    system: str
    developer: str
    user_template: str

    def render_user(self, variables: PromptVariables) -> str:
        rendered = self.user_template
        for key, value in variables.model_dump().items():
            rendered = rendered.replace("{{ " + key + " }}", value)
        return rendered


def load_prompt_template(path: Path) -> PromptTemplate:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PromptTemplate.model_validate(data)
```

- [ ] **Step 5: Run prompt tests**

Run:

```bash
uv run pytest tests/test_prompt_loader.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/prompts app/integrations tests/test_prompt_loader.py
git commit -m "feat: add yaml prompt loader"
```

## Task 7: OpenAI Client Adapter

**Files:**
- Create: `app/integrations/llm/openai_client.py`
- Create: `tests/test_openai_client.py`

- [ ] **Step 1: Write failing OpenAI adapter test**

Create `tests/test_openai_client.py`:

```python
from app.integrations.llm.openai_client import OpenAILLMClient, SummaryRequest


class FakeResponse:
    output_text = (
        '{"title":"Claude Code updated","bullets":["Added CLI flag"],'
        '"breaking_changes":[],"links":["https://github.com/example/repo"],"confidence":"high"}'
    )
    usage = type("Usage", (), {"input_tokens": 10, "output_tokens": 12})()


class FakeResponses:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return FakeResponse()


class FakeOpenAI:
    def __init__(self) -> None:
        self.responses = FakeResponses()


async def test_openai_client_builds_responses_request(prompt_template):
    fake_openai = FakeOpenAI()
    client = OpenAILLMClient(openai_client=fake_openai)

    result = await client.summarize_update(
        SummaryRequest(
            prompt=prompt_template,
            repo_full_name="anthropics/claude-code",
            update_type="release",
            source="release",
            language="ru",
            style="short_technical",
            summary_preferences="breaking changes",
            update_payload="Release notes",
        )
    )

    assert result.summary.title == "Claude Code updated"
    assert result.input_tokens == 10
    assert result.output_tokens == 12
    assert fake_openai.responses.kwargs["model"] == "gpt-5.4-mini"
    assert fake_openai.responses.kwargs["reasoning"] == {"effort": "low", "summary": "concise"}
```

Also add this fixture to `tests/test_openai_client.py`:

```python
import pytest
from pathlib import Path

from app.integrations.llm.prompt_loader import load_prompt_template


@pytest.fixture
def prompt_template():
    return load_prompt_template(Path("app/prompts/github_update_summary.v1.yaml"))
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_openai_client.py -v
```

Expected: FAIL because `openai_client.py` does not exist.

- [ ] **Step 3: Implement OpenAI adapter**

Create `app/integrations/llm/openai_client.py`:

```python
import json
from typing import Protocol

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.integrations.llm.prompt_loader import PromptTemplate, PromptVariables
from app.integrations.llm.schemas import GitHubUpdateSummary


class SummaryRequest(BaseModel):
    prompt: PromptTemplate
    repo_full_name: str
    update_type: str
    source: str
    language: str
    style: str
    summary_preferences: str
    update_payload: str


class SummaryResult(BaseModel):
    summary: GitHubUpdateSummary
    input_tokens: int | None = None
    output_tokens: int | None = None


class ResponsesClient(Protocol):
    async def create(self, **kwargs): ...


class OpenAIClientProtocol(Protocol):
    responses: ResponsesClient


class OpenAILLMClient:
    def __init__(self, openai_client: OpenAIClientProtocol | None = None) -> None:
        self._client = openai_client or AsyncOpenAI()

    async def summarize_update(self, request: SummaryRequest) -> SummaryResult:
        prompt = request.prompt
        rendered_user = prompt.render_user(
            PromptVariables(
                repo_full_name=request.repo_full_name,
                update_type=request.update_type,
                source=request.source,
                language=request.language,
                style=request.style,
                summary_preferences=request.summary_preferences,
                update_payload=request.update_payload,
            )
        )

        response = await self._client.responses.create(
            model=prompt.model,
            reasoning={
                "effort": prompt.reasoning.effort,
                "summary": prompt.reasoning.summary,
            },
            text={
                "verbosity": prompt.text.verbosity,
                "format": {
                    "type": "json_schema",
                    "name": "github_update_summary",
                    "schema": GitHubUpdateSummary.model_json_schema(),
                    "strict": True,
                },
            },
            input=[
                {"role": "system", "content": prompt.system},
                {"role": "developer", "content": prompt.developer},
                {"role": "user", "content": rendered_user},
            ],
        )

        summary = GitHubUpdateSummary.model_validate(json.loads(response.output_text))
        usage = getattr(response, "usage", None)
        return SummaryResult(
            summary=summary,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )
```

- [ ] **Step 4: Normalize imports in the test**

Ensure `tests/test_openai_client.py` has imports in this order:

```python
from pathlib import Path

import pytest

from app.integrations.llm.openai_client import OpenAILLMClient, SummaryRequest
from app.integrations.llm.prompt_loader import load_prompt_template
```

- [ ] **Step 5: Run OpenAI tests**

Run:

```bash
uv run pytest tests/test_openai_client.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/integrations/llm/openai_client.py tests/test_openai_client.py
git commit -m "feat: add openai summary adapter"
```

## Task 8: Runtime Entrypoints And Docker Compose

**Files:**
- Create: `app/bot/__init__.py`
- Create: `app/bot/__main__.py`
- Create: `app/worker/__init__.py`
- Create: `app/worker/__main__.py`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create bot entrypoint**

Create `app/bot/__init__.py`:

```python
"""Telegram bot runtime."""
```

Create `app/bot/__main__.py`:

```python
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.config import get_settings
from app.logging import configure_logging

logger = logging.getLogger(__name__)


async def start(message: Message) -> None:
    await message.answer("GitNotifyBot is running. Subscription flows are not implemented in this foundation slice.")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.message.register(start, CommandStart())
    logger.info("starting bot polling")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Create worker entrypoint**

Create `app/worker/__init__.py`:

```python
"""Background worker runtime."""
```

Create `app/worker/__main__.py`:

```python
import asyncio
import logging

from app.config import get_settings
from app.logging import configure_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("worker started")
    while True:
        logger.info("worker heartbeat")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Create Docker Compose**

Create `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: gitnotifybot
      POSTGRES_USER: gitnotifybot
      POSTGRES_PASSWORD: gitnotifybot
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U gitnotifybot -d gitnotifybot"]
      interval: 5s
      timeout: 3s
      retries: 10

  bot:
    image: python:3.12-slim
    working_dir: /app
    command: sh -c "pip install uv && uv sync && uv run python -m app.bot"
    env_file: .env
    volumes:
      - .:/app
    depends_on:
      postgres:
        condition: service_healthy

  worker:
    image: python:3.12-slim
    working_dir: /app
    command: sh -c "pip install uv && uv sync && uv run python -m app.worker"
    env_file: .env
    volumes:
      - .:/app
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  postgres_data:
```

- [ ] **Step 4: Verify module imports**

Run:

```bash
uv run python -m compileall app tests
```

Expected: command exits 0.

- [ ] **Step 5: Run full foundation checks**

Run:

```bash
uv run pytest
uv run ruff check .
```

Expected: both commands exit 0.

- [ ] **Step 6: Commit**

```bash
git add app/bot app/worker docker-compose.yml
git commit -m "feat: add bot and worker entrypoints"
```

## Task 9: Final Verification

**Files:**
- No code changes expected.

- [ ] **Step 1: Confirm repository status**

Run:

```bash
git status --short --branch
```

Expected: clean working tree on `main`.

- [ ] **Step 2: Run all tests**

Run:

```bash
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 3: Run lint**

Run:

```bash
uv run ruff check .
```

Expected: no lint errors.

- [ ] **Step 4: Run import compilation**

Run:

```bash
uv run python -m compileall app tests
```

Expected: command exits 0.

- [ ] **Step 5: Push commits**

Run:

```bash
git push
```

Expected: local `main` pushed to `origin/main`.

## Self-Review Notes

Spec coverage in this foundation plan:

- Covers modular monolith package structure.
- Covers settings and env names from the spec.
- Covers PostgreSQL schema from the spec.
- Covers deduplicated `github_sources.source_key` rule.
- Covers OpenAI provider abstraction foundation and YAML prompts with reasoning config.
- Covers bot and worker runtime split.
- Covers Docker Compose.
- Covers focused tests.

Deferred to follow-up plans:

- Full Telegram button UX and FSM flows.
- GitHub API clients and update detection.
- Scheduler due-check loop.
- Notification fanout and Telegram formatting.
- i18n message catalogs.
- Admin commands.
