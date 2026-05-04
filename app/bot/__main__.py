import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import router
from app.config import get_settings
from app.integrations.github import GitHubClient
from app.logging import configure_logging
from app.storage.session import create_session_factory

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    session_factory = create_session_factory(settings)
    github_client = GitHubClient(settings.github_token)
    logger.info("starting bot polling")
    await dispatcher.start_polling(
        bot,
        github_client=github_client,
        session_factory=session_factory,
    )


if __name__ == "__main__":
    asyncio.run(main())
