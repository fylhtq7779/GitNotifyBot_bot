"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_telegram_user_id"), "users", ["telegram_user_id"], unique=True)

    op.create_table(
        "chats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("summary_language", sa.String(length=16), server_default="ru", nullable=False),
        sa.Column(
            "summary_style", sa.String(length=64), server_default="short_technical", nullable=False
        ),
        sa.Column("summary_preferences", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chats_telegram_chat_id"), "chats", ["telegram_chat_id"], unique=True)

    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=512), nullable=False),
        sa.Column("html_url", sa.String(length=1024), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner", "name", name="uq_repositories_owner_name"),
    )
    op.create_index(op.f("ix_repositories_full_name"), "repositories", ["full_name"], unique=True)
    op.create_index(op.f("ix_repositories_name"), "repositories", ["name"], unique=False)
    op.create_index(op.f("ix_repositories_owner"), "repositories", ["owner"], unique=False)

    op.create_table(
        "chat_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "user_id", name="uq_chat_members_chat_user"),
    )
    op.create_index(op.f("ix_chat_members_chat_id"), "chat_members", ["chat_id"], unique=False)
    op.create_index(op.f("ix_chat_members_user_id"), "chat_members", ["user_id"], unique=False)

    op.create_table(
        "github_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_key", sa.String(length=1024), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("etag", sa.String(length=512), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("rate_limited_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_github_sources_source_key"), "github_sources", ["source_key"], unique=True
    )
    op.create_index(
        op.f("ix_github_sources_source_type"), "github_sources", ["source_type"], unique=False
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("github_source_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("check_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["github_source_id"], ["github_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "github_source_id", name="uq_subscriptions_chat_source"),
    )
    op.create_index(op.f("ix_subscriptions_chat_id"), "subscriptions", ["chat_id"], unique=False)
    op.create_index(op.f("ix_subscriptions_mode"), "subscriptions", ["mode"], unique=False)
    op.create_index(
        op.f("ix_subscriptions_next_check_at"), "subscriptions", ["next_check_at"], unique=False
    )

    op.create_table(
        "updates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("github_source_id", sa.Integer(), nullable=False),
        sa.Column("update_type", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("from_sha", sa.String(length=255), nullable=True),
        sa.Column("to_sha", sa.String(length=255), nullable=True),
        sa.Column("release_tag", sa.String(length=255), nullable=True),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["github_source_id"], ["github_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_source_id", "external_id", name="uq_updates_source_external"),
    )
    op.create_index(op.f("ix_updates_update_type"), "updates", ["update_type"], unique=False)

    op.create_table(
        "subscription_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("last_seen_release_id", sa.String(length=255), nullable=True),
        sa.Column("last_seen_tag", sa.String(length=255), nullable=True),
        sa.Column("last_seen_file_sha", sa.String(length=255), nullable=True),
        sa.Column("last_seen_commit_sha", sa.String(length=255), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id"),
    )

    op.create_table(
        "llm_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("update_id", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("style", sa.String(length=64), nullable=False),
        sa.Column("preferences_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_id", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("reasoning_effort", sa.String(length=32), nullable=False),
        sa.Column("text_verbosity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["update_id"], ["updates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "update_id",
            "language",
            "style",
            "preferences_hash",
            "prompt_version",
            name="uq_llm_summaries_cache_key",
        ),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("update_id", sa.Integer(), nullable=False),
        sa.Column("llm_summary_id", sa.Integer(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["llm_summary_id"], ["llm_summaries.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["update_id"], ["updates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "update_id", name="uq_notifications_chat_update"),
    )
    op.create_index(op.f("ix_notifications_chat_id"), "notifications", ["chat_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_chat_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("llm_summaries")
    op.drop_table("subscription_state")
    op.drop_index(op.f("ix_updates_update_type"), table_name="updates")
    op.drop_table("updates")
    op.drop_index(op.f("ix_subscriptions_next_check_at"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_mode"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_chat_id"), table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index(op.f("ix_github_sources_source_type"), table_name="github_sources")
    op.drop_index(op.f("ix_github_sources_source_key"), table_name="github_sources")
    op.drop_table("github_sources")
    op.drop_index(op.f("ix_chat_members_user_id"), table_name="chat_members")
    op.drop_index(op.f("ix_chat_members_chat_id"), table_name="chat_members")
    op.drop_table("chat_members")
    op.drop_index(op.f("ix_repositories_owner"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_name"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_full_name"), table_name="repositories")
    op.drop_table("repositories")
    op.drop_index(op.f("ix_chats_telegram_chat_id"), table_name="chats")
    op.drop_table("chats")
    op.drop_index(op.f("ix_users_telegram_user_id"), table_name="users")
    op.drop_table("users")
