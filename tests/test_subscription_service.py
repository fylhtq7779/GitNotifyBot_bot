from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.application.subscriptions import (
    AddFileSubscriptionResult,
    AddReleaseSubscriptionResult,
    SubscriptionListItem,
    add_file_subscription,
    add_release_subscription,
    delete_chat_subscription,
    list_chat_subscriptions,
    reschedule_chat_subscriptions_now,
)
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


@dataclass(frozen=True)
class FakeGitHubFileContents:
    path: str
    sha: str
    size: int | None
    html_url: str | None
    download_url: str | None


class FakeGitHubClient:
    def __init__(
        self,
        *,
        file_contents: FakeGitHubFileContents | None = None,
    ) -> None:
        self._file_contents = file_contents

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

    async def get_file_contents(
        self, ref: GitHubRepositoryRef, *, path: str, branch: str
    ) -> FakeGitHubFileContents:
        if self._file_contents is None:
            return FakeGitHubFileContents(
                path=path,
                sha="abcdef0123456789",
                size=42,
                html_url=f"https://github.com/{ref.full_name}/blob/{branch}/{path}",
                download_url=f"https://raw.githubusercontent.com/{ref.full_name}/{branch}/{path}",
            )
        return self._file_contents


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
        source_key = f"github:releases:{repository.full_name.lower()}"
        source = next(
            (item for item in self.sources if item.source_key == source_key),
            None,
        )
        if source is None:
            source = GitHubSource(
                id=self._allocate_id(),
                repository_id=repository.id,
                source_type="releases",
                source_key=source_key,
            )
            self.sources.append(source)
        return source

    async def get_or_create_file_source(
        self, repository: Repository, *, branch: str, file_path: str
    ) -> GitHubSource:
        normalized = file_path.strip("/")
        source_key = (
            f"github:file:{repository.full_name.lower()}:{branch}:{normalized}"
        )
        source = next(
            (item for item in self.sources if item.source_key == source_key),
            None,
        )
        if source is None:
            source = GitHubSource(
                id=self._allocate_id(),
                repository_id=repository.id,
                source_type="file",
                source_key=source_key,
                branch=branch,
                file_path=normalized,
            )
            self.sources.append(source)
        return source

    async def get_or_create_subscription(
        self,
        *,
        chat: Chat,
        repository: Repository,
        source: GitHubSource,
        mode: str,
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
            mode=mode,
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

    async def ensure_file_state(
        self,
        subscription: Subscription,
        *,
        last_seen_file_sha: str,
    ) -> SubscriptionState:
        state = SubscriptionState(
            id=self._allocate_id(),
            subscription_id=subscription.id,
            last_seen_file_sha=last_seen_file_sha,
        )
        self.states.append(state)
        return state

    async def list_chat_subscriptions(
        self, *, telegram_chat_id: int
    ) -> list[SubscriptionListItem]:
        chat = next(
            (item for item in self.chats if item.telegram_chat_id == telegram_chat_id),
            None,
        )
        if chat is None:
            return []
        result: list[SubscriptionListItem] = []
        for sub in self.subscriptions:
            if sub.chat_id != chat.id:
                continue
            repository = next(item for item in self.repositories if item.id == sub.repository_id)
            state = next(
                (item for item in self.states if item.subscription_id == sub.id),
                None,
            )
            result.append(
                SubscriptionListItem(
                    subscription_id=sub.id,
                    repository_full_name=repository.full_name,
                    repository_html_url=repository.html_url,
                    mode=sub.mode,
                    last_seen_tag=state.last_seen_tag if state else None,
                    last_seen_file_sha=getattr(state, "last_seen_file_sha", None),
                    last_checked_at=None,
                    next_check_at=getattr(sub, "next_check_at", datetime.now(UTC)),
                    status=getattr(sub, "status", "active"),
                )
            )
        return result

    async def reschedule_chat_subscriptions_now(
        self, *, telegram_chat_id: int, now: datetime
    ) -> int:
        chat = next(
            (item for item in self.chats if item.telegram_chat_id == telegram_chat_id),
            None,
        )
        if chat is None:
            return 0
        affected = 0
        for sub in self.subscriptions:
            if sub.chat_id != chat.id:
                continue
            if getattr(sub, "status", "active") != "active":
                continue
            sub.next_check_at = now
            affected += 1
        return affected

    async def delete_chat_subscription(
        self, *, telegram_chat_id: int, subscription_id: int
    ) -> str | None:
        chat = next(
            (item for item in self.chats if item.telegram_chat_id == telegram_chat_id),
            None,
        )
        if chat is None:
            return None
        sub = next(
            (
                item
                for item in self.subscriptions
                if item.id == subscription_id and item.chat_id == chat.id
            ),
            None,
        )
        if sub is None:
            return None
        repository = next(item for item in self.repositories if item.id == sub.repository_id)
        self.subscriptions.remove(sub)
        self.states = [item for item in self.states if item.subscription_id != sub.id]
        return repository.full_name

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


@pytest.mark.asyncio
async def test_list_chat_subscriptions_returns_items_for_chat() -> None:
    store = FakeSubscriptionStore()
    await add_release_subscription(
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
    # Provide next_check_at on the in-memory subscription
    store.subscriptions[0].next_check_at = datetime.now(UTC) + timedelta(minutes=30)

    items = await list_chat_subscriptions(store=store, telegram_chat_id=42)

    assert len(items) == 1
    assert items[0].repository_full_name == "anthropics/claude-code"
    assert items[0].mode == "releases"
    assert items[0].last_seen_tag == "v1.2.3"


@pytest.mark.asyncio
async def test_list_chat_subscriptions_returns_empty_for_unknown_chat() -> None:
    store = FakeSubscriptionStore()

    items = await list_chat_subscriptions(store=store, telegram_chat_id=999)

    assert items == []


@pytest.mark.asyncio
async def test_delete_chat_subscription_removes_only_matching_chat() -> None:
    store = FakeSubscriptionStore()
    await add_release_subscription(
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
    subscription_id = store.subscriptions[0].id

    rejected = await delete_chat_subscription(
        store=store, telegram_chat_id=999, subscription_id=subscription_id
    )
    assert rejected is None
    assert len(store.subscriptions) == 1

    removed = await delete_chat_subscription(
        store=store, telegram_chat_id=42, subscription_id=subscription_id
    )
    assert removed == "anthropics/claude-code"
    assert store.subscriptions == []


@pytest.mark.asyncio
async def test_reschedule_chat_subscriptions_now_resets_next_check_at() -> None:
    store = FakeSubscriptionStore()
    await add_release_subscription(
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
    store.subscriptions[0].status = "active"
    store.subscriptions[0].next_check_at = datetime.now(UTC) + timedelta(hours=2)
    far_future = store.subscriptions[0].next_check_at

    affected = await reschedule_chat_subscriptions_now(store=store, telegram_chat_id=42)

    assert affected == 1
    assert store.subscriptions[0].next_check_at < far_future


@pytest.mark.asyncio
async def test_reschedule_chat_subscriptions_now_returns_zero_for_unknown_chat() -> None:
    store = FakeSubscriptionStore()

    affected = await reschedule_chat_subscriptions_now(store=store, telegram_chat_id=999)

    assert affected == 0


@pytest.mark.asyncio
async def test_add_file_subscription_creates_records_with_baseline_sha() -> None:
    store = FakeSubscriptionStore()

    result = await add_file_subscription(
        store=store,
        github_client=FakeGitHubClient(
            file_contents=FakeGitHubFileContents(
                path="docs/index.md",
                sha="0123456789abcdef",
                size=1024,
                html_url="https://github.com/octo/repo/blob/main/docs/index.md",
                download_url="https://raw.githubusercontent.com/octo/repo/main/docs/index.md",
            )
        ),
        repository_ref=GitHubRepositoryRef(owner="octo", name="repo"),
        file_path="/docs/index.md",
        telegram_chat_id=42,
        chat_type="private",
        chat_title=None,
        telegram_user_id=100,
        username="octocat",
        first_name="Octo",
        last_name=None,
        language_code="ru",
    )

    assert isinstance(result, AddFileSubscriptionResult)
    assert result.repository_full_name == "octo/repo"
    assert result.branch == "main"
    assert result.file_path == "docs/index.md"
    assert result.file_sha == "0123456789abcdef"
    assert result.created is True
    assert len(store.sources) == 1
    assert store.sources[0].source_type == "file"
    assert store.sources[0].file_path == "docs/index.md"
    assert store.sources[0].branch == "main"
    assert len(store.subscriptions) == 1
    assert store.subscriptions[0].mode == "file"
    assert len(store.states) == 1
    assert store.states[0].last_seen_file_sha == "0123456789abcdef"
