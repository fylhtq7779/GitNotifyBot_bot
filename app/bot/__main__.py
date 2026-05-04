import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.config import get_settings
from app.logging import configure_logging

logger = logging.getLogger(__name__)


async def start(message: Message) -> None:
    await message.answer(
        "GitNotifyBot is running. Subscription flows are not implemented in this foundation slice."
    )


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.message.register(start, CommandStart())
    logger.info("starting bot polling")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
