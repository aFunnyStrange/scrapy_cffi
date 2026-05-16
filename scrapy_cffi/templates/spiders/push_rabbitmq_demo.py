"""
Push ingress URLs into the demo RabbitMQ queue (plain UTF-8 URL bytes, same as redis RPUSH).

Environment:
  SCRAPY_CFFI_AMQP_URL      default amqp://guest:guest@127.0.0.1:5672/
  SCRAPY_CFFI_RABBIT_INGRESS default scrapy_cffi (matches rabbitmq_queue in demo spiders)
  SCRAPY_CFFI_START_URL     default http://127.0.0.1:8002 (mock server)
"""
import asyncio
import os

from scrapy_cffi.mq.rabbitmq import RabbitMQManager


async def _main() -> None:
    url = os.environ.get("SCRAPY_CFFI_START_URL", "http://127.0.0.1:8002")
    amqp = os.environ.get("SCRAPY_CFFI_AMQP_URL", "amqp://guest:guest@127.0.0.1:5672/")
    queue = os.environ.get("SCRAPY_CFFI_RABBIT_INGRESS", "scrapy_cffi")

    mgr = RabbitMQManager(
        rabbitmq_url=amqp,
        exchange_name="scrapy_cffi",
        prefetch_count=1,
        persist=True,
    )
    try:
        await mgr.connect()
        await mgr.rpush(queue, url.encode("utf-8"))
    finally:
        await mgr.close()
    print(f"Pushed {url!r} to queue {queue!r}")


if __name__ == "__main__":
    asyncio.run(_main())
