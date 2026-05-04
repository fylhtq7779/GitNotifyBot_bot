import asyncio
import logging

from app.config import get_settings
from app.logging import configure_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("worker started")
    while True:
        logger.info("worker heartbeat")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
