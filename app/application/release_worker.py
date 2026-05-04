import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    GitHubSourceType,
    NotificationStatus,
    SubscriptionStatus,
    SummaryStatus,
    UpdateType,
)
from app.domain.github import GitHubRepositoryRef
from app.storage.models import (
    Chat,
    GitHubSource,
    LLMSummary,
    Notification,
    Repository,
    Subscription,
    SubscriptionState,
    Update,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DueReleaseSubscription:
    subscription_id: int
    chat_id: int
    telegram_chat_id: int
    repository_id: int
    github_source_id: int
    owner: str
    name: str
    full_name: str
    html_url: str
    check_interval_minutes: int
    next_check_at: datetime
    last_seen_release_id: str | None
    last_seen_tag: str | None
    summary_language: str
    summary_style: str
    summary_preferences: str | None
    has_state: bool = True


@dataclass(frozen=True)
class ReleasePollingResult:
    processed: int = 0
    unchanged: int = 0
    notified: int = 0
    failed: int = 0


@dataclass(frozen=True)
class CachedReleaseSummary:
    llm_summary_id: int
    summary_text: str


@dataclass(frozen=True)
class SummaryToPersist:
    update_id: int
    language: str
    style: str
    preferences_hash: str
    prompt_id: str
    prompt_version: str
    model_name: str
    reasoning_effort: str
    text_verbosity: str
    status: str
    summary_text: str | None
    error_message: str | None
    input_tokens: int | None
    output_tokens: int | None


class GitHubRelease(Protocol):
    release_id: str | None
    tag_name: str | None
    name: str | None
    html_url: str | None
    body: str | None


class GitHubClient(Protocol):
    async def get_latest_release(self, ref: GitHubRepositoryRef) -> GitHubRelease | None:
        raise NotImplementedError


class TelegramClient(Protocol):
    async def send_message(self, chat_id: int, text: str) -> int:
        raise NotImplementedError


class ReleaseSummary(Protocol):
    title: str
    bullets: list[str]
    breaking_changes: list[str]
    links: list[str]
    confidence: str
    prompt_id: str
    prompt_version: str
    model_name: str
    reasoning_effort: str
    text_verbosity: str
    input_tokens: int | None
    output_tokens: int | None


class ReleaseSummarizer(Protocol):
    async def summarize_release(
        self,
        *,
        repository_full_name: str,
        tag_name: str | None,
        release_name: str | None,
        body: str | None,
        html_url: str | None,
        language: str,
        style: str,
        preferences: str,
    ) -> ReleaseSummary:
        raise NotImplementedError


class ReleasePollingStore(Protocol):
    async def list_due_release_subscriptions(
        self, *, now: datetime, limit: int
    ) -> list[DueReleaseSubscription]:
        raise NotImplementedError

    async def mark_release_subscription_checked(
        self, *, due: DueReleaseSubscription, now: datetime
    ) -> None:
        raise NotImplementedError

    async def baseline_release_subscription(
        self,
        *,
        due: DueReleaseSubscription,
        release_id: str | None,
        tag_name: str | None,
        now: datetime,
    ) -> None:
        raise NotImplementedError

    async def get_or_create_release_update(
        self,
        *,
        due: DueReleaseSubscription,
        release_id: str,
        tag_name: str | None,
        title: str | None,
        url: str | None,
        raw_payload: dict[str, Any],
    ) -> int:
        raise NotImplementedError

    async def find_cached_release_summary(
        self,
        *,
        update_id: int,
        language: str,
        style: str,
        preferences_hash: str,
        prompt_version: str,
    ) -> CachedReleaseSummary | None:
        raise NotImplementedError

    async def save_release_summary(self, summary: SummaryToPersist) -> int:
        raise NotImplementedError

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
        raise NotImplementedError

    async def mark_release_subscription_failed(
        self, *, due: DueReleaseSubscription, now: datetime, error_message: str
    ) -> None:
        raise NotImplementedError


class SqlAlchemyReleasePollingStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_due_release_subscriptions(
        self, *, now: datetime, limit: int
    ) -> list[DueReleaseSubscription]:
        rows = await self._session.execute(
            select(
                Subscription.id,
                Chat.id,
                Chat.telegram_chat_id,
                Repository.id,
                GitHubSource.id,
                Repository.owner,
                Repository.name,
                Repository.full_name,
                Repository.html_url,
                Subscription.check_interval_minutes,
                Subscription.next_check_at,
                SubscriptionState.id,
                SubscriptionState.last_seen_release_id,
                SubscriptionState.last_seen_tag,
                Chat.summary_language,
                Chat.summary_style,
                Chat.summary_preferences,
            )
            .join(Chat, Chat.id == Subscription.chat_id)
            .join(Repository, Repository.id == Subscription.repository_id)
            .join(GitHubSource, GitHubSource.id == Subscription.github_source_id)
            .outerjoin(
                SubscriptionState,
                SubscriptionState.subscription_id == Subscription.id,
            )
            .where(
                Subscription.status == SubscriptionStatus.ACTIVE.value,
                Subscription.mode == GitHubSourceType.RELEASES.value,
                GitHubSource.source_type == GitHubSourceType.RELEASES.value,
                Chat.is_active.is_(True),
                Subscription.next_check_at <= now,
            )
            .order_by(Subscription.next_check_at, Subscription.id)
            .limit(limit)
        )
        return [
            DueReleaseSubscription(
                subscription_id=subscription_id,
                chat_id=chat_id,
                telegram_chat_id=telegram_chat_id,
                repository_id=repository_id,
                github_source_id=github_source_id,
                owner=owner,
                name=name,
                full_name=full_name,
                html_url=html_url,
                check_interval_minutes=check_interval_minutes,
                next_check_at=next_check_at,
                last_seen_release_id=last_seen_release_id,
                last_seen_tag=last_seen_tag,
                summary_language=summary_language,
                summary_style=summary_style,
                summary_preferences=summary_preferences,
                has_state=state_id is not None,
            )
            for (
                subscription_id,
                chat_id,
                telegram_chat_id,
                repository_id,
                github_source_id,
                owner,
                name,
                full_name,
                html_url,
                check_interval_minutes,
                next_check_at,
                state_id,
                last_seen_release_id,
                last_seen_tag,
                summary_language,
                summary_style,
                summary_preferences,
            ) in rows.all()
        ]

    async def mark_release_subscription_checked(
        self, *, due: DueReleaseSubscription, now: datetime
    ) -> None:
        await self._touch_subscription(due, now)
        await self._touch_source_success(due, now)
        await self._session.flush()

    async def baseline_release_subscription(
        self,
        *,
        due: DueReleaseSubscription,
        release_id: str | None,
        tag_name: str | None,
        now: datetime,
    ) -> None:
        state = await self._session.scalar(
            select(SubscriptionState).where(
                SubscriptionState.subscription_id == due.subscription_id
            )
        )
        if state is None:
            state = SubscriptionState(subscription_id=due.subscription_id)
            self._session.add(state)
        state.last_seen_release_id = release_id
        state.last_seen_tag = tag_name
        await self._touch_subscription(due, now)
        await self._touch_source_success(due, now)
        await self._session.flush()

    async def get_or_create_release_update(
        self,
        *,
        due: DueReleaseSubscription,
        release_id: str,
        tag_name: str | None,
        title: str | None,
        url: str | None,
        raw_payload: dict[str, Any],
    ) -> int:
        update = await self._session.scalar(
            select(Update).where(
                Update.github_source_id == due.github_source_id,
                Update.external_id == release_id,
            )
        )
        if update is None:
            update = Update(
                github_source_id=due.github_source_id,
                update_type=UpdateType.RELEASE.value,
                external_id=release_id,
                title=title,
                url=url,
                release_tag=tag_name,
                raw_payload_json=raw_payload,
            )
            self._session.add(update)
            await self._session.flush()
        return update.id

    async def find_cached_release_summary(
        self,
        *,
        update_id: int,
        language: str,
        style: str,
        preferences_hash: str,
        prompt_version: str,
    ) -> CachedReleaseSummary | None:
        row = await self._session.scalar(
            select(LLMSummary).where(
                LLMSummary.update_id == update_id,
                LLMSummary.language == language,
                LLMSummary.style == style,
                LLMSummary.preferences_hash == preferences_hash,
                LLMSummary.prompt_version == prompt_version,
                LLMSummary.status == SummaryStatus.SUCCESS.value,
            )
        )
        if row is None or row.summary_text is None:
            return None
        return CachedReleaseSummary(llm_summary_id=row.id, summary_text=row.summary_text)

    async def save_release_summary(self, summary: SummaryToPersist) -> int:
        existing = await self._session.scalar(
            select(LLMSummary).where(
                LLMSummary.update_id == summary.update_id,
                LLMSummary.language == summary.language,
                LLMSummary.style == summary.style,
                LLMSummary.preferences_hash == summary.preferences_hash,
                LLMSummary.prompt_version == summary.prompt_version,
            )
        )
        if existing is None:
            existing = LLMSummary(
                update_id=summary.update_id,
                language=summary.language,
                style=summary.style,
                preferences_hash=summary.preferences_hash,
                prompt_id=summary.prompt_id,
                prompt_version=summary.prompt_version,
            )
            self._session.add(existing)
        existing.model_name = summary.model_name
        existing.reasoning_effort = summary.reasoning_effort
        existing.text_verbosity = summary.text_verbosity
        existing.status = summary.status
        existing.summary_text = summary.summary_text
        existing.error_message = summary.error_message
        existing.input_tokens = summary.input_tokens
        existing.output_tokens = summary.output_tokens
        await self._session.flush()
        return existing.id

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
        notification = await self._session.scalar(
            select(Notification).where(
                Notification.chat_id == chat_id,
                Notification.update_id == update_id,
            )
        )
        if notification is None:
            notification = Notification(
                chat_id=chat_id,
                subscription_id=subscription_id,
                update_id=update_id,
            )
            self._session.add(notification)

        notification.llm_summary_id = llm_summary_id
        notification.telegram_message_id = telegram_message_id
        notification.status = status
        notification.error_message = error_message
        notification.sent_at = sent_at
        await self._session.flush()

    async def mark_release_subscription_failed(
        self, *, due: DueReleaseSubscription, now: datetime, error_message: str
    ) -> None:
        source = await self._session.get(GitHubSource, due.github_source_id)
        if source is not None:
            source.last_checked_at = now
            source.last_error_at = now
            source.last_error_message = error_message[:2000]
        await self._touch_subscription(due, now)
        await self._session.flush()

    async def _touch_subscription(self, due: DueReleaseSubscription, now: datetime) -> None:
        subscription = await self._session.get(Subscription, due.subscription_id)
        if subscription is not None:
            subscription.next_check_at = now + timedelta(minutes=due.check_interval_minutes)

    async def _touch_source_success(self, due: DueReleaseSubscription, now: datetime) -> None:
        source = await self._session.get(GitHubSource, due.github_source_id)
        if source is not None:
            source.last_checked_at = now
            source.last_success_at = now
            source.last_error_message = None


async def process_due_release_subscriptions(
    *,
    store: ReleasePollingStore,
    github_client: GitHubClient,
    telegram_client: TelegramClient,
    summarizer: ReleaseSummarizer | None = None,
    now: datetime | None = None,
    limit: int = 50,
) -> ReleasePollingResult:
    checked_at = now or datetime.now(UTC)
    due_subscriptions = await store.list_due_release_subscriptions(now=checked_at, limit=limit)
    processed = unchanged = notified = failed = 0

    for due in due_subscriptions:
        processed += 1
        try:
            release = await github_client.get_latest_release(
                GitHubRepositoryRef(owner=due.owner, name=due.name)
            )
            if release is None or not _release_has_changed(due, release):
                await store.mark_release_subscription_checked(due=due, now=checked_at)
                unchanged += 1
                continue

            if not due.has_state:
                await store.baseline_release_subscription(
                    due=due,
                    release_id=release.release_id,
                    tag_name=release.tag_name,
                    now=checked_at,
                )
                unchanged += 1
                continue

            release_id = release.release_id or release.tag_name
            if release_id is None:
                await store.mark_release_subscription_checked(due=due, now=checked_at)
                unchanged += 1
                continue

            url = _release_url(due, release)
            update_id = await store.get_or_create_release_update(
                due=due,
                release_id=release_id,
                tag_name=release.tag_name,
                title=_release_title(due, release),
                url=url,
                raw_payload=_release_payload(release),
            )

            llm_summary_id, message_text = await _build_message(
                due=due,
                release=release,
                update_id=update_id,
                url=url,
                store=store,
                summarizer=summarizer,
            )

            await store.baseline_release_subscription(
                due=due,
                release_id=release.release_id,
                tag_name=release.tag_name,
                now=checked_at,
            )
            try:
                message_id = await telegram_client.send_message(
                    due.telegram_chat_id, message_text
                )
            except Exception as exc:
                failed += 1
                await store.record_notification(
                    chat_id=due.chat_id,
                    subscription_id=due.subscription_id,
                    update_id=update_id,
                    llm_summary_id=llm_summary_id,
                    telegram_message_id=None,
                    status=NotificationStatus.FAILED.value,
                    error_message=str(exc),
                    sent_at=None,
                )
            else:
                notified += 1
                await store.record_notification(
                    chat_id=due.chat_id,
                    subscription_id=due.subscription_id,
                    update_id=update_id,
                    llm_summary_id=llm_summary_id,
                    telegram_message_id=message_id,
                    status=NotificationStatus.SENT.value,
                    error_message=None,
                    sent_at=checked_at,
                )
        except Exception as exc:
            failed += 1
            await store.mark_release_subscription_failed(
                due=due,
                now=checked_at,
                error_message=str(exc),
            )

    return ReleasePollingResult(
        processed=processed,
        unchanged=unchanged,
        notified=notified,
        failed=failed,
    )


async def _build_message(
    *,
    due: DueReleaseSubscription,
    release: GitHubRelease,
    update_id: int,
    url: str,
    store: ReleasePollingStore,
    summarizer: ReleaseSummarizer | None,
) -> tuple[int | None, str]:
    fallback_text = _fallback_notification_text(due, release, url)
    if summarizer is None:
        return None, fallback_text

    preferences = due.summary_preferences or ""
    preferences_hash = hashlib.sha256(preferences.encode("utf-8")).hexdigest()

    try:
        summary = await summarizer.summarize_release(
            repository_full_name=due.full_name,
            tag_name=release.tag_name,
            release_name=getattr(release, "name", None),
            body=release.body,
            html_url=getattr(release, "html_url", None),
            language=due.summary_language,
            style=due.summary_style,
            preferences=preferences,
        )
    except Exception as exc:
        logger.warning(
            "release summary generation failed",
            extra={
                "subscription_id": due.subscription_id,
                "update_id": update_id,
                "error": str(exc),
            },
        )
        await store.save_release_summary(
            SummaryToPersist(
                update_id=update_id,
                language=due.summary_language,
                style=due.summary_style,
                preferences_hash=preferences_hash,
                prompt_id="github_update_summary",
                prompt_version="unknown",
                model_name="unknown",
                reasoning_effort="unknown",
                text_verbosity="unknown",
                status=SummaryStatus.FAILED.value,
                summary_text=None,
                error_message=str(exc)[:2000],
                input_tokens=None,
                output_tokens=None,
            )
        )
        return None, fallback_text

    summary_payload = json.dumps(
        {
            "title": summary.title,
            "bullets": summary.bullets,
            "breaking_changes": summary.breaking_changes,
            "links": summary.links,
            "confidence": summary.confidence,
        },
        ensure_ascii=False,
    )

    llm_summary_id = await store.save_release_summary(
        SummaryToPersist(
            update_id=update_id,
            language=due.summary_language,
            style=due.summary_style,
            preferences_hash=preferences_hash,
            prompt_id=summary.prompt_id,
            prompt_version=summary.prompt_version,
            model_name=summary.model_name,
            reasoning_effort=summary.reasoning_effort,
            text_verbosity=summary.text_verbosity,
            status=SummaryStatus.SUCCESS.value,
            summary_text=summary_payload,
            error_message=None,
            input_tokens=summary.input_tokens,
            output_tokens=summary.output_tokens,
        )
    )
    return llm_summary_id, _format_summary_message(due, release, url, summary)


def _release_has_changed(due: DueReleaseSubscription, release: GitHubRelease) -> bool:
    if release.release_id is not None and due.last_seen_release_id is not None:
        return release.release_id != due.last_seen_release_id
    if release.tag_name is not None and due.last_seen_tag is not None:
        return release.tag_name != due.last_seen_tag
    return release.release_id is not None or release.tag_name is not None


def _release_title(due: DueReleaseSubscription, release: GitHubRelease) -> str:
    return f"{due.full_name} {release.tag_name or release.release_id or 'release'}"


def _release_url(due: DueReleaseSubscription, release: GitHubRelease) -> str:
    html_url = getattr(release, "html_url", None)
    if isinstance(html_url, str) and html_url:
        return html_url
    if release.tag_name:
        return f"{due.html_url}/releases/tag/{release.tag_name}"
    return f"{due.html_url}/releases"


def _release_payload(release: GitHubRelease) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "release_id": release.release_id,
        "tag_name": release.tag_name,
    }
    name = getattr(release, "name", None)
    html_url = getattr(release, "html_url", None)
    body = getattr(release, "body", None)
    if isinstance(name, str):
        payload["name"] = name
    if isinstance(html_url, str):
        payload["html_url"] = html_url
    if isinstance(body, str):
        payload["body"] = body
    return payload


def _fallback_notification_text(
    due: DueReleaseSubscription, release: GitHubRelease, release_url: str
) -> str:
    label = release.tag_name or release.release_id
    label_part = f" — {label}" if label else ""
    return (
        f"✨ Обновился репозиторий {due.full_name}{label_part}\n\n"
        f"Сводка временно недоступна, открой релиз по ссылке.\n\n"
        f"🔗 {release_url}"
    )


def _format_summary_message(
    due: DueReleaseSubscription,
    release: GitHubRelease,
    release_url: str,
    summary: ReleaseSummary,
) -> str:
    label = release.tag_name or release.release_id
    label_part = f" — {label}" if label else ""
    lines: list[str] = [f"✨ Обновился репозиторий {due.full_name}{label_part}"]
    if summary.title and summary.title.strip():
        lines.append("")
        lines.append(summary.title.strip())
    if summary.bullets:
        lines.append("")
        lines.append("Что нового:")
        lines.extend(f"• {item.strip()}" for item in summary.bullets if item.strip())
    if summary.breaking_changes:
        lines.append("")
        lines.append("⚠️ Что может сломаться:")
        lines.extend(f"• {item.strip()}" for item in summary.breaking_changes if item.strip())
    lines.append("")
    lines.append(f"🔗 {release_url}")
    return "\n".join(lines)
