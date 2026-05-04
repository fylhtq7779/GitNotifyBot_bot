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
