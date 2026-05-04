from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.application.release_worker import (
    DueReleaseSubscription,
    ReleasePollingResult,
    process_due_release_subscriptions,
)
from app.domain.github import GitHubRepositoryRef


@dataclass(frozen=True)
class FakeRelease:
    release_id: str | None
    tag_name: str | None


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


class FakeReleasePollingStore:
    def __init__(self, due: list[DueReleaseSubscription]) -> None:
        self.due = due
        self.no_change_calls: list[tuple[int, datetime]] = []
        self.baselines: list[tuple[int, str | None, str | None, datetime]] = []
        self.updates: list[tuple[int, str, str | None, str | None, dict]] = []
        self.notifications: list[
            tuple[int, int, int, int | None, str, str | None, datetime | None]
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

    async def record_notification(
        self,
        *,
        chat_id: int,
        subscription_id: int,
        update_id: int,
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
                telegram_message_id,
                status,
                error_message,
                sent_at,
            )
        )


def due_subscription(
    *,
    last_seen_release_id: str | None = "1",
    last_seen_tag: str | None = "v1.0.0",
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
    )


@pytest.mark.asyncio
async def test_process_due_release_subscription_advances_poll_for_unchanged_release() -> None:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    store = FakeReleasePollingStore([due_subscription()])
    github = FakeGitHubClient(FakeRelease(release_id="1", tag_name="v1.0.0"))
    telegram = FakeTelegramClient()

    result = await process_due_release_subscriptions(
        store=store,
        github_client=github,
        telegram_client=telegram,
        now=now,
    )

    assert result == ReleasePollingResult(processed=1, unchanged=1, notified=0, failed=0)
    assert github.requested_refs == [GitHubRepositoryRef(owner="octo", name="repo")]
    assert store.no_change_calls == [(10, now)]
    assert store.updates == []
    assert store.notifications == []
    assert telegram.messages == []


@pytest.mark.asyncio
async def test_process_due_release_subscription_sends_notification_for_new_release() -> None:
    now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    store = FakeReleasePollingStore([due_subscription()])
    github = FakeGitHubClient(FakeRelease(release_id="2", tag_name="v1.1.0"))
    telegram = FakeTelegramClient()

    result = await process_due_release_subscriptions(
        store=store,
        github_client=github,
        telegram_client=telegram,
        now=now,
    )

    assert result == ReleasePollingResult(processed=1, unchanged=0, notified=1, failed=0)
    assert store.updates == [
        (
            40,
            "2",
            "v1.1.0",
            "octo/repo v1.1.0",
            {"release_id": "2", "tag_name": "v1.1.0"},
        )
    ]
    assert store.baselines == [(10, "2", "v1.1.0", now)]
    assert telegram.messages == [
        (
            12345,
            "New release for octo/repo: v1.1.0\nhttps://github.com/octo/repo/releases/tag/v1.1.0",
        )
    ]
    assert store.notifications == [(20, 10, 700, 555, "sent", None, now)]
