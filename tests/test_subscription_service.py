from dataclasses import dataclass

import pytest

from app.application.subscriptions import AddReleaseSubscriptionResult, add_release_subscription
from app.domain.github import GitHubRepositoryRef
from app.storage.models import Chat, GitHubSource, Repository, Subscription, SubscriptionState, User


@dataclass(frozen=True)
class FakeGitHubRepository:
    owner: str
    name: str
    full_name: str
    html_url: str
    default_branch: str
    is_archived: bool


@dataclass(frozen=True)
class FakeGitHubRelease:
    release_id: str | None
    tag_name: str | None


class FakeGitHubClient:
    async def get_repository(self, ref: GitHubRepositoryRef) -> FakeGitHubRepository:
        return FakeGitHubRepository(
            owner=ref.owner,
            name=ref.name,
            full_name=ref.full_name,
            html_url=f"https://github.com/{ref.full_name}",
            default_branch="main",
            is_archived=False,
        )

    async def get_latest_release(
        self, ref: GitHubRepositoryRef
    ) -> FakeGitHubRelease | None:
        return FakeGitHubRelease(release_id="123456", tag_name="v1.2.3")


class FakeSubscriptionStore:
    def __init__(self) -> None:
        self.users: list[User] = []
        self.chats: list[Chat] = []
        self.repositories: list[Repository] = []
        self.sources: list[GitHubSource] = []
        self.subscriptions: list[Subscription] = []
        self.states: list[SubscriptionState] = []
        self._next_id = 1

    async def get_or_create_user(
        self,
        *,
        telegram_user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
    ) -> User:
        user = next(
            (item for item in self.users if item.telegram_user_id == telegram_user_id),
            None,
        )
        if user is None:
            user = User(
                id=self._allocate_id(),
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=language_code,
            )
            self.users.append(user)
        return user

    async def get_or_create_chat(
        self,
        *,
        telegram_chat_id: int,
        chat_type: str,
        title: str | None,
        created_by_user_id: int,
    ) -> Chat:
        chat = next(
            (item for item in self.chats if item.telegram_chat_id == telegram_chat_id),
            None,
        )
        if chat is None:
            chat = Chat(
                id=self._allocate_id(),
                telegram_chat_id=telegram_chat_id,
                type=chat_type,
                title=title,
                created_by_user_id=created_by_user_id,
            )
            self.chats.append(chat)
        return chat

    async def upsert_repository(self, github_repository: FakeGitHubRepository) -> Repository:
        repository = next(
            (item for item in self.repositories if item.full_name == github_repository.full_name),
            None,
        )
        if repository is None:
            repository = Repository(
                id=self._allocate_id(),
                owner=github_repository.owner,
                name=github_repository.name,
                full_name=github_repository.full_name,
                html_url=github_repository.html_url,
                default_branch=github_repository.default_branch,
                is_archived=github_repository.is_archived,
            )
            self.repositories.append(repository)
        return repository

    async def get_or_create_release_source(self, repository: Repository) -> GitHubSource:
        source = next(
            (
                item
                for item in self.sources
                if item.source_key == "github:releases:anthropics/claude-code"
            ),
            None,
        )
        if source is None:
            source = GitHubSource(
                id=self._allocate_id(),
                repository_id=repository.id,
                source_type="releases",
                source_key="github:releases:anthropics/claude-code",
            )
            self.sources.append(source)
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
        subscription = next(
            (
                item
                for item in self.subscriptions
                if item.chat_id == chat.id and item.github_source_id == source.id
            ),
            None,
        )
        if subscription is not None:
            return subscription, False

        subscription = Subscription(
            id=self._allocate_id(),
            chat_id=chat.id,
            repository_id=repository.id,
            github_source_id=source.id,
            mode="releases",
            check_interval_minutes=check_interval_minutes,
            created_by_user_id=created_by_user_id,
        )
        self.subscriptions.append(subscription)
        return subscription, True

    async def ensure_release_state(
        self,
        subscription: Subscription,
        *,
        last_seen_release_id: str | None,
        last_seen_tag: str | None,
    ) -> SubscriptionState:
        state = SubscriptionState(
            id=self._allocate_id(),
            subscription_id=subscription.id,
            last_seen_release_id=last_seen_release_id,
            last_seen_tag=last_seen_tag,
        )
        self.states.append(state)
        return state

    def _allocate_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value


@pytest.mark.asyncio
async def test_add_release_subscription_creates_records_with_latest_release_baseline() -> None:
    store = FakeSubscriptionStore()

    result = await add_release_subscription(
        store=store,
        github_client=FakeGitHubClient(),
        repository_ref=GitHubRepositoryRef(owner="anthropics", name="claude-code"),
        telegram_chat_id=42,
        chat_type="private",
        chat_title=None,
        telegram_user_id=100,
        username="octocat",
        first_name="Octo",
        last_name=None,
        language_code="ru",
    )

    assert result == AddReleaseSubscriptionResult(
        repository_full_name="anthropics/claude-code",
        repository_html_url="https://github.com/anthropics/claude-code",
        default_branch="main",
        latest_release_tag="v1.2.3",
        created=True,
    )
    assert len(store.users) == 1
    assert len(store.chats) == 1
    assert len(store.repositories) == 1
    assert len(store.sources) == 1
    assert len(store.subscriptions) == 1
    assert store.states[0].last_seen_release_id == "123456"
    assert store.states[0].last_seen_tag == "v1.2.3"
