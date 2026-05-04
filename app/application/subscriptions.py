from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import GitHubSourceType, SubscriptionStatus
from app.domain.github import GitHubRepositoryRef, build_source_key
from app.storage.models import Chat, GitHubSource, Repository, Subscription, SubscriptionState, User

DEFAULT_CHECK_INTERVAL_MINUTES = 30


class GitHubRepository(Protocol):
    owner: str
    name: str
    full_name: str
    html_url: str
    default_branch: str
    is_archived: bool


class GitHubRelease(Protocol):
    release_id: str | None
    tag_name: str | None


class GitHubClient(Protocol):
    async def get_repository(self, ref: GitHubRepositoryRef) -> GitHubRepository:
        raise NotImplementedError

    async def get_latest_release(self, ref: GitHubRepositoryRef) -> GitHubRelease | None:
        raise NotImplementedError


class SubscriptionStore(Protocol):
    async def get_or_create_user(
        self,
        *,
        telegram_user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
    ) -> User:
        raise NotImplementedError

    async def get_or_create_chat(
        self,
        *,
        telegram_chat_id: int,
        chat_type: str,
        title: str | None,
        created_by_user_id: int,
    ) -> Chat:
        raise NotImplementedError

    async def upsert_repository(self, github_repository: GitHubRepository) -> Repository:
        raise NotImplementedError

    async def get_or_create_release_source(self, repository: Repository) -> GitHubSource:
        raise NotImplementedError

    async def get_or_create_subscription(
        self,
        *,
        chat: Chat,
        repository: Repository,
        source: GitHubSource,
        created_by_user_id: int,
        check_interval_minutes: int,
    ) -> tuple[Subscription, bool]:
        raise NotImplementedError

    async def ensure_release_state(
        self,
        subscription: Subscription,
        *,
        last_seen_release_id: str | None,
        last_seen_tag: str | None,
    ) -> SubscriptionState:
        raise NotImplementedError


@dataclass(frozen=True)
class AddReleaseSubscriptionResult:
    repository_full_name: str
    repository_html_url: str
    default_branch: str
    latest_release_tag: str | None
    created: bool


class SqlAlchemySubscriptionStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_user(
        self,
        *,
        telegram_user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
    ) -> User:
        user = await self._session.scalar(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        if user is None:
            user = User(telegram_user_id=telegram_user_id)
            self._session.add(user)

        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.language_code = language_code
        await self._session.flush()
        return user

    async def get_or_create_chat(
        self,
        *,
        telegram_chat_id: int,
        chat_type: str,
        title: str | None,
        created_by_user_id: int,
    ) -> Chat:
        chat = await self._session.scalar(
            select(Chat).where(Chat.telegram_chat_id == telegram_chat_id)
        )
        if chat is None:
            chat = Chat(
                telegram_chat_id=telegram_chat_id,
                created_by_user_id=created_by_user_id,
            )
            self._session.add(chat)

        chat.type = chat_type
        chat.title = title
        chat.is_active = True
        await self._session.flush()
        return chat

    async def upsert_repository(self, github_repository: GitHubRepository) -> Repository:
        repository = await self._session.scalar(
            select(Repository).where(Repository.full_name == github_repository.full_name)
        )
        if repository is None:
            repository = Repository(full_name=github_repository.full_name)
            self._session.add(repository)

        repository.owner = github_repository.owner
        repository.name = github_repository.name
        repository.html_url = github_repository.html_url
        repository.default_branch = github_repository.default_branch
        repository.is_archived = github_repository.is_archived
        repository.last_seen_at = datetime.now(UTC)
        await self._session.flush()
        return repository

    async def get_or_create_release_source(self, repository: Repository) -> GitHubSource:
        source_key = build_source_key(
            GitHubSourceType.RELEASES,
            repository.owner,
            repository.name,
        )
        source = await self._session.scalar(
            select(GitHubSource).where(GitHubSource.source_key == source_key)
        )
        if source is None:
            source = GitHubSource(
                repository_id=repository.id,
                source_type=GitHubSourceType.RELEASES.value,
                source_key=source_key,
            )
            self._session.add(source)
            await self._session.flush()
        return source

    async def get_or_create_subscription(
        self,
        *,
        chat: Chat,
        repository: Repository,
        source: GitHubSource,
        created_by_user_id: int,
        check_interval_minutes: int,
    ) -> tuple[Subscription, bool]:
        subscription = await self._session.scalar(
            select(Subscription).where(
                Subscription.chat_id == chat.id,
                Subscription.github_source_id == source.id,
            )
        )
        if subscription is not None:
            return subscription, False

        subscription = Subscription(
            chat_id=chat.id,
            repository_id=repository.id,
            github_source_id=source.id,
            mode=GitHubSourceType.RELEASES.value,
            status=SubscriptionStatus.ACTIVE.value,
            check_interval_minutes=check_interval_minutes,
            next_check_at=datetime.now(UTC) + timedelta(minutes=check_interval_minutes),
            created_by_user_id=created_by_user_id,
        )
        self._session.add(subscription)
        await self._session.flush()
        return subscription, True

    async def ensure_release_state(
        self,
        subscription: Subscription,
        *,
        last_seen_release_id: str | None,
        last_seen_tag: str | None,
    ) -> SubscriptionState:
        state = await self._session.scalar(
            select(SubscriptionState).where(
                SubscriptionState.subscription_id == subscription.id
            )
        )
        if state is None:
            state = SubscriptionState(subscription_id=subscription.id)
            self._session.add(state)

        state.last_seen_release_id = last_seen_release_id
        state.last_seen_tag = last_seen_tag
        await self._session.flush()
        return state


async def add_release_subscription(
    *,
    store: SubscriptionStore,
    github_client: GitHubClient,
    repository_ref: GitHubRepositoryRef,
    telegram_chat_id: int,
    chat_type: str,
    chat_title: str | None,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    language_code: str | None,
    check_interval_minutes: int = DEFAULT_CHECK_INTERVAL_MINUTES,
) -> AddReleaseSubscriptionResult:
    github_repository = await github_client.get_repository(repository_ref)
    latest_release = await github_client.get_latest_release(repository_ref)

    user = await store.get_or_create_user(
        telegram_user_id=telegram_user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        language_code=language_code,
    )
    chat = await store.get_or_create_chat(
        telegram_chat_id=telegram_chat_id,
        chat_type=chat_type,
        title=chat_title,
        created_by_user_id=user.id,
    )
    repository = await store.upsert_repository(github_repository)
    source = await store.get_or_create_release_source(repository)
    subscription, created = await store.get_or_create_subscription(
        chat=chat,
        repository=repository,
        source=source,
        created_by_user_id=user.id,
        check_interval_minutes=check_interval_minutes,
    )
    if created:
        await store.ensure_release_state(
            subscription,
            last_seen_release_id=latest_release.release_id if latest_release else None,
            last_seen_tag=latest_release.tag_name if latest_release else None,
        )

    return AddReleaseSubscriptionResult(
        repository_full_name=github_repository.full_name,
        repository_html_url=github_repository.html_url,
        default_branch=github_repository.default_branch,
        latest_release_tag=latest_release.tag_name if latest_release else None,
        created=created,
    )
