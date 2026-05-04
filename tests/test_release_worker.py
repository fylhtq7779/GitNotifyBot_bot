from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from app.application.release_worker import (
    CachedReleaseSummary,
    DueReleaseSubscription,
    ReleasePollingResult,
    SummaryToPersist,
    process_due_release_subscriptions,
)
from app.domain.github import GitHubRepositoryRef


@dataclass(frozen=True)
class FakeRelease:
    release_id: str | None
    tag_name: str | None
    name: str | None = None
    html_url: str | None = None
    body: str | None = None


class FakeGitHubClient:
    def __init__(self, release: FakeRelease | None) -> None:
        self.release = release
        self.requested_refs: list[GitHubRepositoryRef] = []

    async def get_latest_release(self, ref: GitHubRepositoryRef) -> FakeRelease | None:
        self.requested_refs.append(ref)
        return self.release


class FakeTelegramClient:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> int:
        self.messages.append((chat_id, text))
        return 555


@dataclass
class FakeSummary:
    title: str = "Release summary"
    bullets: list[str] = field(default_factory=lambda: ["bullet one", "bullet two"])
    breaking_changes: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    confidence: str = "high"
    prompt_id: str = "github_update_summary"
    prompt_version: str = "v1"
    model_name: str = "gpt-test"
    reasoning_effort: str = "low"
    text_verbosity: str = "low"
    input_tokens: int | None = 11
    output_tokens: int | None = 13


class FakeSummarizer:
    def __init__(
        self,
        summary: FakeSummary | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self.summary = summary or FakeSummary()
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    async def summarize_release(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.summary


class FakeReleasePollingStore:
    def __init__(self, due: list[DueReleaseSubscription]) -> None:
        self.due = due
        self.no_change_calls: list[tuple[int, datetime]] = []
        self.baselines: list[tuple[int, str | None, str | None, datetime]] = []
        self.updates: list[tuple[int, str, str | None, str | None, dict]] = []
        self.summaries: list[SummaryToPersist] = []
        self.cached_summary: CachedReleaseSummary | None = None
        self.notifications: list[
            tuple[int, int, int, int | None, int | None, str, str | None, datetime | None]
        ] = []

    async def list_due_release_subscriptions(
        self, *, now: datetime, limit: int
    ) -> list[DueReleaseSubscription]:
        return self.due[:limit]

    async def mark_release_subscription_checked(
        self, *, due: DueReleaseSubscription, now: datetime
    ) -> None:
        self.no_change_calls.append((due.subscription_id, now))

    async def baseline_release_subscription(
        self,
        *,
        due: DueReleaseSubscription,
        release_id: str | None,
        tag_name: str | None,
        now: datetime,
    ) -> None:
        self.baselines.append((due.subscription_id, release_id, tag_name, now))

    async def get_or_create_release_update(
        self,
        *,
        due: DueReleaseSubscription,
        release_id: str,
        tag_name: str | None,
        title: str | None,
        url: str | None,
        raw_payload: dict,
    ) -> int:
        update_id = 700 + len(self.updates)
        self.updates.append((due.github_source_id, release_id, tag_name, title, raw_payload))
        return update_id

    async def find_cached_release_summary(
        self,
        *,
        update_id: int,
        language: str,
        style: str,
        preferences_hash: str,
        prompt_version: str,
    ) -> CachedReleaseSummary | None:
        return self.cached_summary

    async def save_release_summary(self, summary: SummaryToPersist) -> int:
        self.summaries.append(summary)
        return 9000 + len(self.summaries)

    async def record_notification(
        self,
        *,
        chat_id: int,
        subscription_id: int,
        update_id: int,
        llm_summary_id: int | None,
        telegram_message_id: int | None,
        status: str,
        error_message: str | None,
        sent_at: datetime | None,
    ) -> None:
        self.notifications.append(
            (
                chat_id,
                subscription_id,
                update_id,
                llm_summary_id,
                telegram_message_id,
                status,
                error_message,
                sent_at,
            )
        )

    async def mark_release_subscription_failed(
        self, *, due: DueReleaseSubscription, now: datetime, error_message: str
    ) -> None:
        pass


def due_subscription(
    *,
    last_seen_release_id: str | None = "1",
    last_seen_tag: str | None = "v1.0.0",
    summary_language: str = "ru",
    summary_style: str = "short_technical",
    summary_preferences: str | None = None,
) -> DueReleaseSubscription:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    return DueReleaseSubscription(
        subscription_id=10,
        chat_id=20,
        telegram_chat_id=12345,
        repository_id=30,
        github_source_id=40,
        owner="octo",
        name="repo",
        full_name="octo/repo",
        html_url="https://github.com/octo/repo",
        check_interval_minutes=30,
        next_check_at=now - timedelta(minutes=1),
        last_seen_release_id=last_seen_release_id,
        last_seen_tag=last_seen_tag,
        summary_language=summary_language,
        summary_style=summary_style,
        summary_preferences=summary_preferences,
    )


@pytest.mark.asyncio
async def test_unchanged_release_advances_poll_without_llm() -> None:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    store = FakeReleasePollingStore([due_subscription()])
    github = FakeGitHubClient(FakeRelease(release_id="1", tag_name="v1.0.0"))
    telegram = FakeTelegramClient()
    summarizer = FakeSummarizer()

    result = await process_due_release_subscriptions(
        store=store,
        github_client=github,
        telegram_client=telegram,
        summarizer=summarizer,
        now=now,
    )

    assert result == ReleasePollingResult(processed=1, unchanged=1, notified=0, failed=0)
    assert github.requested_refs == [GitHubRepositoryRef(owner="octo", name="repo")]
    assert store.no_change_calls == [(10, now)]
    assert summarizer.calls == []
    assert store.summaries == []
    assert store.notifications == []


@pytest.mark.asyncio
async def test_new_release_calls_summarizer_and_sends_rich_message() -> None:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    due = due_subscription()
    store = FakeReleasePollingStore([due])
    github = FakeGitHubClient(
        FakeRelease(
            release_id="2",
            tag_name="v1.1.0",
            name="Release 1.1.0",
            html_url="https://github.com/octo/repo/releases/tag/v1.1.0",
            body="### Changes\n- new flag",
        )
    )
    telegram = FakeTelegramClient()
    summarizer = FakeSummarizer()

    result = await process_due_release_subscriptions(
        store=store,
        github_client=github,
        telegram_client=telegram,
        summarizer=summarizer,
        now=now,
    )

    assert result == ReleasePollingResult(processed=1, unchanged=0, notified=1, failed=0)
    assert len(summarizer.calls) == 1
    call = summarizer.calls[0]
    assert call["repository_full_name"] == "octo/repo"
    assert call["language"] == "ru"
    assert call["body"] == "### Changes\n- new flag"
    assert len(store.summaries) == 1
    persisted = store.summaries[0]
    assert persisted.status == "success"
    assert persisted.summary_text is not None and "Release summary" in persisted.summary_text

    chat_id, message_text = telegram.messages[0]
    assert chat_id == 12345
    assert "Обновился репозиторий octo/repo" in message_text
    assert "v1.1.0" in message_text
    assert "Release summary" in message_text
    assert "• bullet one" in message_text
    assert "https://github.com/octo/repo/releases/tag/v1.1.0" in message_text

    assert store.notifications[0][3] == 9001  # llm_summary_id from FakeReleasePollingStore
    assert store.notifications[0][5] == "sent"


@pytest.mark.asyncio
async def test_summarizer_failure_falls_back_to_plain_message() -> None:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    store = FakeReleasePollingStore([due_subscription()])
    github = FakeGitHubClient(
        FakeRelease(
            release_id="2",
            tag_name="v1.1.0",
            html_url="https://github.com/octo/repo/releases/tag/v1.1.0",
            body=None,
        )
    )
    telegram = FakeTelegramClient()
    summarizer = FakeSummarizer(raise_exc=RuntimeError("openai down"))

    result = await process_due_release_subscriptions(
        store=store,
        github_client=github,
        telegram_client=telegram,
        summarizer=summarizer,
        now=now,
    )

    assert result == ReleasePollingResult(processed=1, unchanged=0, notified=1, failed=0)
    assert len(store.summaries) == 1
    assert store.summaries[0].status == "failed"
    assert store.summaries[0].error_message == "openai down"

    _, message_text = telegram.messages[0]
    assert "Обновился репозиторий octo/repo" in message_text
    assert "v1.1.0" in message_text
    assert "https://github.com/octo/repo/releases/tag/v1.1.0" in message_text
    assert store.notifications[0][3] is None  # no llm_summary_id when fallback
    assert store.notifications[0][5] == "sent"


@pytest.mark.asyncio
async def test_first_baseline_skips_notification_and_summarizer() -> None:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    due = due_subscription(last_seen_release_id=None, last_seen_tag=None)
    due_no_state = DueReleaseSubscription(
        subscription_id=due.subscription_id,
        chat_id=due.chat_id,
        telegram_chat_id=due.telegram_chat_id,
        repository_id=due.repository_id,
        github_source_id=due.github_source_id,
        owner=due.owner,
        name=due.name,
        full_name=due.full_name,
        html_url=due.html_url,
        check_interval_minutes=due.check_interval_minutes,
        next_check_at=due.next_check_at,
        last_seen_release_id=None,
        last_seen_tag=None,
        summary_language=due.summary_language,
        summary_style=due.summary_style,
        summary_preferences=due.summary_preferences,
        has_state=False,
    )
    store = FakeReleasePollingStore([due_no_state])
    github = FakeGitHubClient(FakeRelease(release_id="42", tag_name="v2.0.0"))
    telegram = FakeTelegramClient()
    summarizer = FakeSummarizer()

    result = await process_due_release_subscriptions(
        store=store,
        github_client=github,
        telegram_client=telegram,
        summarizer=summarizer,
        now=now,
    )

    assert result == ReleasePollingResult(processed=1, unchanged=1, notified=0, failed=0)
    assert summarizer.calls == []
    assert telegram.messages == []
    assert store.baselines == [(10, "42", "v2.0.0", now)]
