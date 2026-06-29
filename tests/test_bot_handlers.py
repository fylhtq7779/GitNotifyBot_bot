from datetime import UTC, datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from app.bot.handlers import MAIN_MENU_TEXT, router

TOKEN = "123456789:AAH1234567890abcdefghijklmnopqrstuvw"
CHAT = Chat(id=555, type="private")
USER = User(id=42, is_bot=False, first_name="Andrey", username="andrey")


class RecordingSession(BaseSession):
    """Сессия Bot API без сети: пишет исходящие вызовы, возвращает заглушку Message."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict]] = []

    async def close(self) -> None:
        pass

    async def make_request(self, bot, method, timeout=None):
        data = method.model_dump(exclude_none=True)
        self.calls.append((type(method).__name__, data))
        return Message(
            message_id=len(self.calls),
            date=datetime.now(UTC),
            chat=CHAT,
            from_user=User(id=1, is_bot=True, first_name="bot"),
            text=data.get("text", ""),
        )

    async def stream_content(self, *args, **kwargs):
        yield b""


def _callback_update(data: str) -> Update:
    carrier = Message(
        message_id=900,
        date=datetime.now(UTC),
        chat=CHAT,
        from_user=User(id=1, is_bot=True, first_name="bot"),
        text="prev",
    )
    return Update(
        update_id=1,
        callback_query=CallbackQuery(
            id="1", from_user=USER, chat_instance="ci", message=carrier, data=data
        ),
    )


# router - модульный синглтон, его можно прикрепить только к одному диспетчеру,
# поэтому bot/dispatcher живут на весь модуль, а тесты смотрят срез новых вызовов.
@pytest.fixture(scope="module")
def bot() -> Bot:
    return Bot(token=TOKEN, session=RecordingSession())


@pytest.fixture(scope="module")
def dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    return dp


async def test_stale_callback_is_answered_and_returns_to_menu(bot, dispatcher) -> None:
    # Кнопка из старого сообщения / выбор режима после рестарта: состояния нет,
    # ни один специфичный хендлер не матчится - должен сработать перехватчик.
    before = len(bot.session.calls)
    await dispatcher.feed_update(bot, _callback_update("add:mode:releases"))
    calls = bot.session.calls[before:]

    methods = [name for name, _ in calls]
    # callback обязан быть отвечен (иначе кнопка вечно крутит спиннер)
    assert "AnswerCallbackQuery" in methods
    # и пользователь возвращён в актуальное меню
    sent = [data["text"] for name, data in calls if name == "SendMessage"]
    assert any(text == MAIN_MENU_TEXT for text in sent)


async def test_unknown_callback_does_not_hang(bot, dispatcher) -> None:
    before = len(bot.session.calls)
    await dispatcher.feed_update(bot, _callback_update("totally:unknown:data"))
    calls = bot.session.calls[before:]

    methods = [name for name, _ in calls]
    assert "AnswerCallbackQuery" in methods
