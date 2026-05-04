from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import Chat

SUPPORTED_LANGUAGES: tuple[str, ...] = ("ru", "en")
SUPPORTED_STYLES: tuple[str, ...] = ("short_technical", "detailed")
MAX_PREFERENCES_LENGTH = 500


@dataclass(frozen=True)
class ChatSettings:
    language: str
    style: str
    preferences: str | None


class ChatSettingsStore(Protocol):
    async def get_chat_settings(self, *, telegram_chat_id: int) -> ChatSettings | None:
        raise NotImplementedError

    async def update_chat_summary_language(
        self, *, telegram_chat_id: int, language: str
    ) -> bool:
        raise NotImplementedError

    async def update_chat_summary_style(
        self, *, telegram_chat_id: int, style: str
    ) -> bool:
        raise NotImplementedError

    async def update_chat_summary_preferences(
        self, *, telegram_chat_id: int, preferences: str | None
    ) -> bool:
        raise NotImplementedError


class SqlAlchemyChatSettingsStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_chat_settings(self, *, telegram_chat_id: int) -> ChatSettings | None:
        chat = await self._session.scalar(
            select(Chat).where(Chat.telegram_chat_id == telegram_chat_id)
        )
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
        chat = await self._session.scalar(
            select(Chat).where(Chat.telegram_chat_id == telegram_chat_id)
        )
        if chat is None:
            return False
        chat.summary_language = language
        await self._session.flush()
        return True

    async def update_chat_summary_style(
        self, *, telegram_chat_id: int, style: str
    ) -> bool:
        chat = await self._session.scalar(
            select(Chat).where(Chat.telegram_chat_id == telegram_chat_id)
        )
        if chat is None:
            return False
        chat.summary_style = style
        await self._session.flush()
        return True

    async def update_chat_summary_preferences(
        self, *, telegram_chat_id: int, preferences: str | None
    ) -> bool:
        chat = await self._session.scalar(
            select(Chat).where(Chat.telegram_chat_id == telegram_chat_id)
        )
        if chat is None:
            return False
        chat.summary_preferences = preferences
        await self._session.flush()
        return True


async def get_chat_settings(
    *, store: ChatSettingsStore, telegram_chat_id: int
) -> ChatSettings | None:
    return await store.get_chat_settings(telegram_chat_id=telegram_chat_id)


async def set_chat_summary_language(
    *, store: ChatSettingsStore, telegram_chat_id: int, language: str
) -> bool:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    return await store.update_chat_summary_language(
        telegram_chat_id=telegram_chat_id, language=language
    )


async def set_chat_summary_style(
    *, store: ChatSettingsStore, telegram_chat_id: int, style: str
) -> bool:
    if style not in SUPPORTED_STYLES:
        raise ValueError(f"Unsupported style: {style}")
    return await store.update_chat_summary_style(
        telegram_chat_id=telegram_chat_id, style=style
    )


async def set_chat_summary_preferences(
    *, store: ChatSettingsStore, telegram_chat_id: int, preferences: str | None
) -> bool:
    cleaned = preferences.strip() if isinstance(preferences, str) else None
    if cleaned == "":
        cleaned = None
    if cleaned is not None and len(cleaned) > MAX_PREFERENCES_LENGTH:
        raise ValueError(
            f"Preferences must be at most {MAX_PREFERENCES_LENGTH} characters"
        )
    return await store.update_chat_summary_preferences(
        telegram_chat_id=telegram_chat_id, preferences=cleaned
    )
