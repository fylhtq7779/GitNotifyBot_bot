from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from app.application.file_worker import (
    DueFileSubscription,
    FilePollingResult,
    FileSummaryToPersist,
    process_due_file_subscriptions,
)
from app.domain.github import GitHubRepositoryRef


@dataclass(frozen=True)
class FakeFileContents:
    path: str
    sha: str
    size: int | None = None
    html_url: str | None = None
    download_url: str | None = None


class FakeGitHubClient:
    def __init__(self, contents: FakeFileContents | Exception) -> None:
        self.contents = contents
        self.requested: list[tuple[GitHubRepositoryRef, str, str]] = []

    async def get_file_contents(
        self, ref: GitHubRepositoryRef, *, path: str, branch: str
    ) -> FakeFileContents:
        self.requested.append((ref, path, branch))
        if isinstance(self.contents, Exception):
            raise self.contents
        return self.contents


class FakeTelegramClient:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> int:
        self.messages.append((chat_id, text))
        return 777


@dataclass
class FakeFileSummary:
    title: str = "File update summary"
    bullets: list[str] = field(default_factory=lambda: ["bullet"])
    breaking_changes: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    confidence: str = "high"
    prompt_id: str = "github_update_summary"
    prompt_version: str = "v1"
    model_name: str = "gpt-test"
    reasoning_effort: str = "low"
    text_verbosity: str = "low"
    input_tokens: int | None = 5
    output_tokens: int | None = 7


class FakeFileSummarizer:
    def __init__(
        self,
        summary: FakeFileSummary | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self.summary = summary or FakeFileSummary()
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    async def summarize_file_change(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.summary


class FakeFilePollingStore:
    def __init__(self, due: list[DueFileSubscription]) -> None:
        self.due = due
        self.checked_only: list[tuple[int, datetime]] = []
        self.baselines: list[tuple[int, str, datetime]] = []
        self.updates: list[tuple[int, str, str | None]] = []
        self.summaries: list[FileSummaryToPersist] = []
        self.notifications: list[
            tuple[int, int, int, int | None, int | None, str, str | None, datetime | None]
        ] = []
        self.failures: list[tuple[int, str]] = []

    async def list_due_file_subscriptions(
        self, *, now: datetime, limit: int
    ) -> list[DueFileSubscription]:
        return self.due[:limit]

    async def mark_file_subscription_checked(
        self, *, due: DueFileSubscription, now: datetime
    ) -> None:
        self.checked_only.append((due.subscription_id, now))

    async def baseline_file_subscription(
        self, *, due: DueFileSubscription, sha: str, now: datetime
    ) -> None:
        self.baselines.append((due.subscription_id, sha, now))

    async def get_or_create_file_update(
        self,
        *,
        due: DueFileSubscription,
        new_sha: str,
        previous_sha: str | None,
        title: str | None,
        url: str | None,
        raw_payload: dict,
    ) -> int:
        update_id = 800 + len(self.updates)
        self.updates.append((due.github_source_id, new_sha, previous_sha))
        return update_id

    async def save_file_summary(self, summary: FileSummaryToPersist) -> int:
        self.summaries.append(summary)
        return 9100 + len(self.summaries)

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

    async def mark_file_subscription_failed(
        self, *, due: DueFileSubscription, now: datetime, error_message: str
    ) -> None:
        self.failures.append((due.subscription_id, error_message))


def due_file_subscription(
    *,
    last_seen_file_sha: str | None = "abc1234",
    has_state: bool = True,
) -> DueFileSubscription:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    return DueFileSubscription(
        subscription_id=11,
        chat_id=21,
        telegram_chat_id=42,
        repository_id=31,
        github_source_id=41,
        owner="octo",
        name="repo",
        full_name="octo/repo",
        html_url="https://github.com/octo/repo",
        branch="main",
        file_path="docs/index.md",
        check_interval_minutes=30,
        next_check_at=now - timedelta(minutes=1),
        last_seen_file_sha=last_seen_file_sha,
        summary_language="ru",
        summary_style="short_technical",
        summary_preferences=None,
        has_state=has_state,
    )


@pytest.mark.asyncio
async def test_unchanged_file_advances_poll_without_notification() -> None:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    store = FakeFilePollingStore([due_file_subscription(last_seen_file_sha="abc1234")])
    github = FakeGitHubClient(
        FakeFileContents(path="docs/index.md", sha="abc1234")
    )
    telegram = FakeTelegramClient()

    result = await process_due_file_subscriptions(
        store=store,
        github_client=github,
        telegram_client=telegram,
        summarizer=None,
        now=now,
    )

    assert result == FilePollingResult(processed=1, unchanged=1, notified=0, failed=0)
    assert store.checked_only == [(11, now)]
    assert store.notifications == []
    assert telegram.messages == []


@pytest.mark.asyncio
async def test_first_baseline_skips_notification() -> None:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    store = FakeFilePollingStore(
        [due_file_subscription(last_seen_file_sha=None, has_state=False)]
    )
    github = FakeGitHubClient(
        FakeFileContents(path="docs/index.md", sha="zzz9999")
    )
    telegram = FakeTelegramClient()

    result = await process_due_file_subscriptions(
        store=store,
        github_client=github,
        telegram_client=telegram,
        summarizer=None,
        now=now,
    )

    assert result == FilePollingResult(processed=1, unchanged=1, notified=0, failed=0)
    assert store.baselines == [(11, "zzz9999", now)]
    assert telegram.messages == []


@pytest.mark.asyncio
async def test_changed_file_sends_fallback_when_no_summarizer() -> None:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    store = FakeFilePollingStore([due_file_subscription(last_seen_file_sha="abc1234")])
    github = FakeGitHubClient(
        FakeFileContents(
            path="docs/index.md",
            sha="newsha9999999",
            html_url="https://github.com/octo/repo/blob/main/docs/index.md",
        )
    )
    telegram = FakeTelegramClient()

    result = await process_due_file_subscriptions(
        store=store,
        github_client=github,
        telegram_client=telegram,
        summarizer=None,
        now=now,
    )

    assert result == FilePollingResult(processed=1, unchanged=0, notified=1, failed=0)
    chat_id, message = telegram.messages[0]
    assert chat_id == 42
    assert "Обновился файл docs/index.md в репозитории octo/repo" in message
    assert "Ветка" not in message  # branch not exposed in user-facing text
    assert "https://github.com/octo/repo/blob/main/docs/index.md" in message
    assert store.notifications[0][3] is None
    assert store.notifications[0][5] == "sent"
    assert store.baselines == [(11, "newsha9999999", now)]


@pytest.mark.asyncio
async def test_changed_file_uses_summarizer_when_provided() -> None:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    store = FakeFilePollingStore([due_file_subscription(last_seen_file_sha="abc1234")])
    github = FakeGitHubClient(
        FakeFileContents(path="docs/index.md", sha="newsha9999999")
    )
    telegram = FakeTelegramClient()
    summarizer = FakeFileSummarizer()

    result = await process_due_file_subscriptions(
        store=store,
        github_client=github,
        telegram_client=telegram,
        summarizer=summarizer,
        now=now,
    )

    assert result == FilePollingResult(processed=1, unchanged=0, notified=1, failed=0)
    assert len(summarizer.calls) == 1
    call = summarizer.calls[0]
    assert call["repository_full_name"] == "octo/repo"
    assert call["file_path"] == "docs/index.md"
    assert call["previous_sha"] == "abc1234"
    assert call["new_sha"] == "newsha9999999"
    assert len(store.summaries) == 1
    assert store.summaries[0].status == "success"
    chat_id, message = telegram.messages[0]
    assert chat_id == 42
    assert "Обновился файл docs/index.md в репозитории octo/repo" in message
    assert "File update summary" in message
    assert store.notifications[0][3] == 9101


@pytest.mark.asyncio
async def test_summarizer_failure_falls_back_to_plain_message() -> None:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    store = FakeFilePollingStore([due_file_subscription(last_seen_file_sha="abc1234")])
    github = FakeGitHubClient(FakeFileContents(path="docs/index.md", sha="newsha9999999"))
    telegram = FakeTelegramClient()
    summarizer = FakeFileSummarizer(raise_exc=RuntimeError("openai down"))

    result = await process_due_file_subscriptions(
        store=store,
        github_client=github,
        telegram_client=telegram,
        summarizer=summarizer,
        now=now,
    )

    assert result == FilePollingResult(processed=1, unchanged=0, notified=1, failed=0)
    assert store.summaries[0].status == "failed"
    assert store.summaries[0].error_message == "openai down"
    assert store.notifications[0][3] is None


@pytest.mark.asyncio
async def test_github_failure_marks_subscription_failed() -> None:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    store = FakeFilePollingStore([due_file_subscription(last_seen_file_sha="abc1234")])
    github = FakeGitHubClient(RuntimeError("github 500"))
    telegram = FakeTelegramClient()

    result = await process_due_file_subscriptions(
        store=store,
        github_client=github,
        telegram_client=telegram,
        summarizer=None,
        now=now,
    )

    assert result == FilePollingResult(processed=1, unchanged=0, notified=0, failed=1)
    assert store.failures == [(11, "github 500")]
    assert telegram.messages == []
