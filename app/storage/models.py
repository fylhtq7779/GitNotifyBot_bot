from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
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
    __table_args__ = (
        UniqueConstraint("github_source_id", "external_id", name="uq_updates_source_external"),
    )

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
