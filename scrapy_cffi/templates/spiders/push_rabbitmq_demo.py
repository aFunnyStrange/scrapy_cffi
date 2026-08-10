"""Push one URL into the demo RabbitMQ ingress repository."""

import asyncio
import os

from scrapy_cffi import build_resource_service
from scrapy_cffi.config import RabbitMQInfo
from scrapy_cffi.settings import SettingsInfo


async def _main() -> None:
    """Build the standard resource service and publish one start URL."""
    url = os.environ.get("SCRAPY_CFFI_START_URL", "http://127.0.0.1:8002")
    amqp = os.environ.get(
        "SCRAPY_CFFI_AMQP_URL",
        "amqp://guest:guest@127.0.0.1:5672/",
    )
    queue = os.environ.get("SCRAPY_CFFI_RABBIT_INGRESS", "scrapy_cffi")
    settings = SettingsInfo(RABBITMQ_INFO=RabbitMQInfo(URL=amqp))
    resources = build_resource_service(settings, asyncio.Event())
    await resources.start()
    try:
        if resources.rabbitmq is None:
            raise RuntimeError("RabbitMQ repository is not configured")
        await resources.rabbitmq.push(queue, url.encode("utf-8"))
    finally:
        await resources.close()


if __name__ == "__main__":
    asyncio.run(_main())
