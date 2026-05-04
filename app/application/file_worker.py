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
class DueFileSubscription:
    subscription_id: int
    chat_id: int
    telegram_chat_id: int
    repository_id: int
    github_source_id: int
    owner: str
    name: str
    full_name: str
    html_url: str
    branch: str
    file_path: str
    check_interval_minutes: int
    next_check_at: datetime
    last_seen_file_sha: str | None
    summary_language: str
    summary_style: str
    summary_preferences: str | None
    has_state: bool = True


@dataclass(frozen=True)
class FilePollingResult:
    processed: int = 0
    unchanged: int = 0
    notified: int = 0
    failed: int = 0


@dataclass(frozen=True)
class FileSummaryToPersist:
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


class GitHubFileContents(Protocol):
    path: str
    sha: str
    size: int | None
    html_url: str | None
    download_url: str | None


class GitHubClient(Protocol):
    async def get_file_contents(
        self, ref: GitHubRepositoryRef, *, path: str, branch: str
    ) -> GitHubFileContents:
        raise NotImplementedError


class TelegramClient(Protocol):
    async def send_message(self, chat_id: int, text: str) -> int:
        raise NotImplementedError


class FileSummary(Protocol):
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


class FileSummarizer(Protocol):
    async def summarize_file_change(
        self,
        *,
        repository_full_name: str,
        branch: str,
        file_path: str,
        previous_sha: str | None,
        new_sha: str,
        file_html_url: str | None,
        language: str,
        style: str,
        preferences: str,
    ) -> FileSummary:
        raise NotImplementedError


class FilePollingStore(Protocol):
    async def list_due_file_subscriptions(
        self, *, now: datetime, limit: int
    ) -> list[DueFileSubscription]:
        raise NotImplementedError

    async def mark_file_subscription_checked(
        self, *, due: DueFileSubscription, now: datetime
    ) -> None:
        raise NotImplementedError

    async def baseline_file_subscription(
        self, *, due: DueFileSubscription, sha: str, now: datetime
    ) -> None:
        raise NotImplementedError

    async def get_or_create_file_update(
        self,
        *,
        due: DueFileSubscription,
        new_sha: str,
        previous_sha: str | None,
        title: str | None,
        url: str | None,
        raw_payload: dict[str, Any],
    ) -> int:
        raise NotImplementedError

    async def save_file_summary(self, summary: FileSummaryToPersist) -> int:
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

    async def mark_file_subscription_failed(
        self, *, due: DueFileSubscription, now: datetime, error_message: str
    ) -> None:
        raise NotImplementedError


class SqlAlchemyFilePollingStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_due_file_subscriptions(
        self, *, now: datetime, limit: int
    ) -> list[DueFileSubscription]:
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
                GitHubSource.branch,
                GitHubSource.file_path,
                Subscription.check_interval_minutes,
                Subscription.next_check_at,
                SubscriptionState.id,
                SubscriptionState.last_seen_file_sha,
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
                Subscription.mode == GitHubSourceType.FILE.value,
                GitHubSource.source_type == GitHubSourceType.FILE.value,
                Chat.is_active.is_(True),
                Subscription.next_check_at <= now,
            )
            .order_by(Subscription.next_check_at, Subscription.id)
            .limit(limit)
        )
        result: list[DueFileSubscription] = []
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
            branch,
            file_path,
            check_interval_minutes,
            next_check_at,
            state_id,
            last_seen_file_sha,
            summary_language,
            summary_style,
            summary_preferences,
        ) in rows.all():
            if branch is None or file_path is None:
                continue
            result.append(
                DueFileSubscription(
                    subscription_id=subscription_id,
                    chat_id=chat_id,
                    telegram_chat_id=telegram_chat_id,
                    repository_id=repository_id,
                    github_source_id=github_source_id,
                    owner=owner,
                    name=name,
                    full_name=full_name,
                    html_url=html_url,
                    branch=branch,
                    file_path=file_path,
                    check_interval_minutes=check_interval_minutes,
                    next_check_at=next_check_at,
                    last_seen_file_sha=last_seen_file_sha,
                    summary_language=summary_language,
                    summary_style=summary_style,
                    summary_preferences=summary_preferences,
                    has_state=state_id is not None,
                )
            )
        return result

    async def mark_file_subscription_checked(
        self, *, due: DueFileSubscription, now: datetime
    ) -> None:
        await self._touch_subscription(due, now)
        await self._touch_source_success(due, now)
        await self._session.flush()

    async def baseline_file_subscription(
        self, *, due: DueFileSubscription, sha: str, now: datetime
    ) -> None:
        state = await self._session.scalar(
            select(SubscriptionState).where(
                SubscriptionState.subscription_id == due.subscription_id
            )
        )
        if state is None:
            state = SubscriptionState(subscription_id=due.subscription_id)
            self._session.add(state)
        state.last_seen_file_sha = sha
        await self._touch_subscription(due, now)
        await self._touch_source_success(due, now)
        await self._session.flush()

    async def get_or_create_file_update(
        self,
        *,
        due: DueFileSubscription,
        new_sha: str,
        previous_sha: str | None,
        title: str | None,
        url: str | None,
        raw_payload: dict[str, Any],
    ) -> int:
        update = await self._session.scalar(
            select(Update).where(
                Update.github_source_id == due.github_source_id,
                Update.external_id == new_sha,
            )
        )
        if update is None:
            update = Update(
                github_source_id=due.github_source_id,
                update_type=UpdateType.FILE_CHANGE.value,
                external_id=new_sha,
                title=title,
                url=url,
                from_sha=previous_sha,
                to_sha=new_sha,
                raw_payload_json=raw_payload,
            )
            self._session.add(update)
            await self._session.flush()
        return update.id

    async def save_file_summary(self, summary: FileSummaryToPersist) -> int:
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

    async def mark_file_subscription_failed(
        self, *, due: DueFileSubscription, now: datetime, error_message: str
    ) -> None:
        source = await self._session.get(GitHubSource, due.github_source_id)
        if source is not None:
            source.last_checked_at = now
            source.last_error_at = now
            source.last_error_message = error_message[:2000]
        await self._touch_subscription(due, now)
        await self._session.flush()

    async def _touch_subscription(self, due: DueFileSubscription, now: datetime) -> None:
        subscription = await self._session.get(Subscription, due.subscription_id)
        if subscription is not None:
            subscription.next_check_at = now + timedelta(minutes=due.check_interval_minutes)

    async def _touch_source_success(self, due: DueFileSubscription, now: datetime) -> None:
        source = await self._session.get(GitHubSource, due.github_source_id)
        if source is not None:
            source.last_checked_at = now
            source.last_success_at = now
            source.last_error_message = None


async def process_due_file_subscriptions(
    *,
    store: FilePollingStore,
    github_client: GitHubClient,
    telegram_client: TelegramClient,
    summarizer: FileSummarizer | None = None,
    now: datetime | None = None,
    limit: int = 50,
) -> FilePollingResult:
    checked_at = now or datetime.now(UTC)
    due_subscriptions = await store.list_due_file_subscriptions(now=checked_at, limit=limit)
    processed = unchanged = notified = failed = 0

    for due in due_subscriptions:
        processed += 1
        try:
            contents = await github_client.get_file_contents(
                GitHubRepositoryRef(owner=due.owner, name=due.name),
                path=due.file_path,
                branch=due.branch,
            )
            if not due.has_state or due.last_seen_file_sha is None:
                await store.baseline_file_subscription(
                    due=due, sha=contents.sha, now=checked_at
                )
                unchanged += 1
                continue
            if contents.sha == due.last_seen_file_sha:
                await store.mark_file_subscription_checked(due=due, now=checked_at)
                unchanged += 1
                continue

            file_url = _file_url(due, contents)
            update_id = await store.get_or_create_file_update(
                due=due,
                new_sha=contents.sha,
                previous_sha=due.last_seen_file_sha,
                title=f"{due.full_name}:{due.file_path}",
                url=file_url,
                raw_payload=_file_payload(due, contents),
            )

            llm_summary_id, message_text = await _build_message(
                due=due,
                contents=contents,
                update_id=update_id,
                file_url=file_url,
                store=store,
                summarizer=summarizer,
            )

            await store.baseline_file_subscription(
                due=due, sha=contents.sha, now=checked_at
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
            await store.mark_file_subscription_failed(
                due=due, now=checked_at, error_message=str(exc)
            )

    return FilePollingResult(
        processed=processed,
        unchanged=unchanged,
        notified=notified,
        failed=failed,
    )


async def _build_message(
    *,
    due: DueFileSubscription,
    contents: GitHubFileContents,
    update_id: int,
    file_url: str,
    store: FilePollingStore,
    summarizer: FileSummarizer | None,
) -> tuple[int | None, str]:
    fallback_text = _fallback_text(due, contents, file_url)
    if summarizer is None:
        return None, fallback_text

    preferences = due.summary_preferences or ""
    preferences_hash = hashlib.sha256(preferences.encode("utf-8")).hexdigest()
    try:
        summary = await summarizer.summarize_file_change(
            repository_full_name=due.full_name,
            branch=due.branch,
            file_path=due.file_path,
            previous_sha=due.last_seen_file_sha,
            new_sha=contents.sha,
            file_html_url=contents.html_url,
            language=due.summary_language,
            style=due.summary_style,
            preferences=preferences,
        )
    except Exception as exc:
        logger.warning(
            "file summary generation failed",
            extra={
                "subscription_id": due.subscription_id,
                "update_id": update_id,
                "error": str(exc),
            },
        )
        await store.save_file_summary(
            FileSummaryToPersist(
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
    llm_summary_id = await store.save_file_summary(
        FileSummaryToPersist(
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
    return llm_summary_id, _format_summary_message(due, contents, file_url, summary)


def _file_url(due: DueFileSubscription, contents: GitHubFileContents) -> str:
    if isinstance(contents.html_url, str) and contents.html_url:
        return contents.html_url
    return f"{due.html_url}/blob/{due.branch}/{due.file_path}"


def _file_payload(
    due: DueFileSubscription, contents: GitHubFileContents
) -> dict[str, Any]:
    return {
        "branch": due.branch,
        "file_path": due.file_path,
        "previous_sha": due.last_seen_file_sha,
        "new_sha": contents.sha,
        "size": contents.size,
        "html_url": contents.html_url,
        "download_url": contents.download_url,
    }


def _fallback_text(
    due: DueFileSubscription, contents: GitHubFileContents, file_url: str
) -> str:
    return (
        f"✨ Обновился файл {due.file_path} в репозитории {due.full_name}\n\n"
        f"Сводка временно недоступна, открой файл по ссылке.\n\n"
        f"🔗 {file_url}"
    )


def _format_summary_message(
    due: DueFileSubscription,
    contents: GitHubFileContents,
    file_url: str,
    summary: FileSummary,
) -> str:
    lines: list[str] = [
        f"✨ Обновился файл {due.file_path} в репозитории {due.full_name}"
    ]
    if summary.title and summary.title.strip():
        lines.append("")
        lines.append(summary.title.strip())
    if summary.bullets:
        lines.append("")
        lines.append("Что изменилось:")
        lines.extend(f"• {item.strip()}" for item in summary.bullets if item.strip())
    if summary.breaking_changes:
        lines.append("")
        lines.append("⚠️ Что может сломаться:")
        lines.extend(f"• {item.strip()}" for item in summary.breaking_changes if item.strip())
    lines.append("")
    lines.append(f"🔗 {file_url}")
    return "\n".join(lines)
