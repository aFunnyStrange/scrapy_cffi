import asyncio, json
from . import BaseSpider
from ..core.downloader.internet.request import HttpRequest
from ..hooks import spiders_hooks
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..crawler import Crawler

try:
    import aio_pika
except ImportError as e:
    raise ImportError(
        "Missing aio_pika dependencies. Please install: pip install aio_pika"
    ) from e

class RabbitmqSpider(BaseSpider):
    name = "rabbitmqSpider"
    rabbitmq_queue = "rabbitmq_queue"

    def __init__(self, 
        settings=None, 
        run_py_dir=None, 
        stop_event=None, 
        session_id="", 
        hooks=None,
        mq_url="amqp://guest:guest@localhost/",
        *args, 
        **kwargs
    ):
        super().__init__(
            settings=settings, 
            run_py_dir=run_py_dir, 
            stop_event=stop_event, 
            session_id=session_id,
            hooks=hooks,
            *args, 
            **kwargs
        )
        self.mq_url = mq_url
        self.mq_connection: aio_pika.RobustConnection = None
        self.mq_channel: aio_pika.Channel = None
        self.mq_queue: aio_pika.Queue = None

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            settings=crawler.settings,
            run_py_dir=crawler.run_py_dir,
            stop_event=crawler.stop_event,
            session_id="",
            hooks=spiders_hooks(crawler),
            mq_url=crawler.settings.RABBITMQ_INFO.URL
        )

    async def connect_mq(self):
        self.mq_connection = await aio_pika.connect_robust(self.mq_url)
        self.mq_channel = await self.mq_connection.channel()
        self.mq_queue = await self.mq_channel.declare_queue(
            self.rabbitmq_queue, durable=True, auto_delete=False
        )

    async def start(self, *args, **kwargs):
        if not self.mq_connection:
            await self.connect_mq()

        async with self.mq_queue.iterator() as queue_iter:
            async for message in queue_iter:
                if self.stop_event.is_set():
                    break
                async with message.process():
                    data = message.body
                    request = await self.make_request_from_data(data)
                    if request:
                        yield request

    async def make_request_from_data(self, data: bytes):
        url = data.decode("utf-8")
        return HttpRequest(
            url=url,
            method="GET",
            headers=self.settings.DEFAULT_HEADERS,
            cookies=self.settings.DEFAULT_COOKIES,
            proxies=self.settings.PROXIES,
            timeout=self.settings.TIMEOUT,
            dont_filter=self.settings.DONT_FILTER,
            callback=self.parse,
            errback=self.errRet
        )

    async def send_result_to_mq(self, routing_key: str, data: dict):
        if not self.mq_channel:
            await self.connect_mq()
        exchange = await self.mq_channel.declare_exchange("result_exchange", aio_pika.ExchangeType.DIRECT, durable=True)
        message = aio_pika.Message(
            body=json.dumps(data).encode(), 
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )
        await exchange.publish(message, routing_key=routing_key)

    async def close_mq(self):
        if self.mq_channel:
            await self.mq_channel.close()
        if self.mq_connection:
            await self.mq_connection.close()