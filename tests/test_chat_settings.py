from dataclasses import dataclass

import pytest

from app.application.chat_settings import (
    MAX_PREFERENCES_LENGTH,
    ChatSettings,
    get_chat_settings,
    set_chat_summary_language,
    set_chat_summary_preferences,
    set_chat_summary_style,
)


@dataclass
class FakeChat:
    telegram_chat_id: int
    summary_language: str = "ru"
    summary_style: str = "short_technical"
    summary_preferences: str | None = None


class FakeChatSettingsStore:
    def __init__(self, chats: list[FakeChat]) -> None:
        self.chats = chats

    def _find(self, telegram_chat_id: int) -> FakeChat | None:
        return next(
            (item for item in self.chats if item.telegram_chat_id == telegram_chat_id),
            None,
        )

    async def get_chat_settings(self, *, telegram_chat_id: int) -> ChatSettings | None:
        chat = self._find(telegram_chat_id)
        if chat is None:
            return None
        return ChatSettings(
            language=chat.summary_language,
            style=chat.summary_style,
            preferences=chat.summary_preferences,
        )

    async def update_chat_summary_language(
        self, *, telegram_chat_id: int, language: str
    ) -> bool:
        chat = self._find(telegram_chat_id)
        if chat is None:
            return False
        chat.summary_language = language
        return True

    async def update_chat_summary_style(
        self, *, telegram_chat_id: int, style: str
    ) -> bool:
        chat = self._find(telegram_chat_id)
        if chat is None:
            return False
        chat.summary_style = style
        return True

    async def update_chat_summary_preferences(
        self, *, telegram_chat_id: int, preferences: str | None
    ) -> bool:
        chat = self._find(telegram_chat_id)
        if chat is None:
            return False
        chat.summary_preferences = preferences
        return True


@pytest.mark.asyncio
async def test_set_language_persists() -> None:
    store = FakeChatSettingsStore([FakeChat(telegram_chat_id=42)])

    ok = await set_chat_summary_language(store=store, telegram_chat_id=42, language="en")

    assert ok is True
    settings = await get_chat_settings(store=store, telegram_chat_id=42)
    assert settings is not None and settings.language == "en"


@pytest.mark.asyncio
async def test_set_language_rejects_unsupported() -> None:
    store = FakeChatSettingsStore([FakeChat(telegram_chat_id=42)])

    with pytest.raises(ValueError):
        await set_chat_summary_language(store=store, telegram_chat_id=42, language="de")


@pytest.mark.asyncio
async def test_set_style_persists() -> None:
    store = FakeChatSettingsStore([FakeChat(telegram_chat_id=42)])

    ok = await set_chat_summary_style(store=store, telegram_chat_id=42, style="detailed")

    assert ok is True
    settings = await get_chat_settings(store=store, telegram_chat_id=42)
    assert settings is not None and settings.style == "detailed"


@pytest.mark.asyncio
async def test_set_preferences_trims_and_persists() -> None:
    store = FakeChatSettingsStore([FakeChat(telegram_chat_id=42)])

    ok = await set_chat_summary_preferences(
        store=store, telegram_chat_id=42, preferences="  выделяй breaking changes  "
    )

    assert ok is True
    settings = await get_chat_settings(store=store, telegram_chat_id=42)
    assert settings is not None and settings.preferences == "выделяй breaking changes"


@pytest.mark.asyncio
async def test_set_preferences_clears_when_empty() -> None:
    store = FakeChatSettingsStore(
        [FakeChat(telegram_chat_id=42, summary_preferences="something")]
    )

    ok = await set_chat_summary_preferences(
        store=store, telegram_chat_id=42, preferences=""
    )

    assert ok is True
    settings = await get_chat_settings(store=store, telegram_chat_id=42)
    assert settings is not None and settings.preferences is None


@pytest.mark.asyncio
async def test_set_preferences_rejects_too_long() -> None:
    store = FakeChatSettingsStore([FakeChat(telegram_chat_id=42)])

    with pytest.raises(ValueError):
        await set_chat_summary_preferences(
            store=store,
            telegram_chat_id=42,
            preferences="x" * (MAX_PREFERENCES_LENGTH + 1),
        )


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_chat() -> None:
    store = FakeChatSettingsStore([])

    assert await get_chat_settings(store=store, telegram_chat_id=999) is None
