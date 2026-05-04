import asyncio
import logging

from aiogram import Bot

from app.application.release_worker import (
    ReleasePollingResult,
    SqlAlchemyReleasePollingStore,
    process_due_release_subscriptions,
)
from app.config import get_settings
from app.integrations.github import GitHubClient
from app.logging import configure_logging
from app.storage.session import create_session_factory

logger = logging.getLogger(__name__)


class TelegramNotificationClient:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_message(self, chat_id: int, text: str) -> int:
        message = await self._bot.send_message(chat_id=chat_id, text=text)
        return message.message_id


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    session_factory = create_session_factory(settings)
    github_client = GitHubClient(settings.github_token)
    bot = Bot(token=settings.telegram_bot_token)
    telegram_client = TelegramNotificationClient(bot)
    logger.info("worker started")
    try:
        while True:
            async with session_factory() as session:
                async with session.begin():
                    result = await process_due_release_subscriptions(
                        store=SqlAlchemyReleasePollingStore(session),
                        github_client=github_client,
                        telegram_client=telegram_client,
                    )
            _log_result(result)
            await asyncio.sleep(60)
    finally:
        await bot.session.close()


def _log_result(result: ReleasePollingResult) -> None:
    logger.info(
        "release polling cycle completed",
        extra={
            "processed": result.processed,
            "unchanged": result.unchanged,
            "notified": result.notified,
            "failed": result.failed,
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
