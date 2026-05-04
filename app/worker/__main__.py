import asyncio
import logging
from pathlib import Path

from aiogram import Bot

from app.application.file_worker import (
    FilePollingResult,
    SqlAlchemyFilePollingStore,
    process_due_file_subscriptions,
)
from app.application.release_worker import (
    ReleasePollingResult,
    SqlAlchemyReleasePollingStore,
    process_due_release_subscriptions,
)
from app.config import get_settings
from app.integrations.github import GitHubClient
from app.integrations.llm.openai_client import OpenAILLMClient
from app.integrations.llm.prompt_loader import load_prompt_template
from app.integrations.llm.release_summarizer import OpenAIReleaseSummarizer
from app.logging import configure_logging
from app.storage.session import create_session_factory

logger = logging.getLogger(__name__)

PROMPT_PATH = Path("app/prompts/github_update_summary.v1.yaml")
POLL_INTERVAL_SECONDS = 60


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
    prompt = load_prompt_template(PROMPT_PATH)
    release_summarizer = OpenAIReleaseSummarizer(client=OpenAILLMClient(), prompt=prompt)
    logger.info("worker started")
    try:
        while True:
            async with session_factory() as session:
                async with session.begin():
                    release_result = await process_due_release_subscriptions(
                        store=SqlAlchemyReleasePollingStore(session),
                        github_client=github_client,
                        telegram_client=telegram_client,
                        summarizer=release_summarizer,
                    )
            _log_release_result(release_result)

            async with session_factory() as session:
                async with session.begin():
                    file_result = await process_due_file_subscriptions(
                        store=SqlAlchemyFilePollingStore(session),
                        github_client=github_client,
                        telegram_client=telegram_client,
                        summarizer=None,
                    )
            _log_file_result(file_result)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await bot.session.close()


def _log_release_result(result: ReleasePollingResult) -> None:
    logger.info(
        "release polling cycle completed",
        extra={
            "processed": result.processed,
            "unchanged": result.unchanged,
            "notified": result.notified,
            "failed": result.failed,
        },
    )


def _log_file_result(result: FilePollingResult) -> None:
    logger.info(
        "file polling cycle completed",
        extra={
            "processed": result.processed,
            "unchanged": result.unchanged,
            "notified": result.notified,
            "failed": result.failed,
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
