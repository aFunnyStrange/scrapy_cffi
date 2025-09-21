import asyncio
import inspect
import random
from functools import wraps
from typing import TYPE_CHECKING, Union, List, Dict

try:
    import aio_pika
    from aio_pika import ExchangeType, DeliveryMode
    from aio_pika.exceptions import AMQPConnectionError, ChannelClosed, QueueEmpty
except ImportError as e:
    raise ImportError(
        "Missing aio_pika dependencies. "
        "Please install: pip install aio_pika"
    ) from e

from tenacity import retry, wait_fixed, retry_if_exception_type

if TYPE_CHECKING:
    from ..crawler import Crawler

def auto_retry(func):
    @wraps(func)
    @retry(
        wait=wait_fixed(1),
        retry=retry_if_exception_type((AMQPConnectionError, ChannelClosed)),
        reraise=True
    )
    async def wrapper(self, *args, **kwargs):
        if self.stop_event.is_set():
            raise asyncio.CancelledError("Stop event set, abort RabbitMQ operation")
        try:
            return await func(self, *args, **kwargs)
        except (AMQPConnectionError, ChannelClosed):
            if self.stop_event.is_set():
                raise asyncio.CancelledError("Stop event set during reconnect")
            await self.connect()
            return await func(self, *args, **kwargs)
    return wrapper


class RabbitMQManager:
    def __init__(
        self,
        stop_event: asyncio.Event = None,
        rabbitmq_url: Union[str, List[str]] = None,
        exchange_name: str = "scrapy_cffi",
        exchange_type: ExchangeType = ExchangeType.DIRECT,
        prefetch_count: int = 10,
        persist: bool = False,
        loop: asyncio.AbstractEventLoop = None,
    ):
        self.stop_event = stop_event or asyncio.Event()
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type
        self.prefetch_count = prefetch_count
        self.persist = persist
        self.loop = loop or asyncio.get_event_loop()
        self._lock = asyncio.Lock()

        if isinstance(rabbitmq_url, str):
            self.mq_mode = "single"
            self._mq_nodes = [rabbitmq_url]
        elif isinstance(rabbitmq_url, list):
            self.mq_mode = "cluster"
            if not rabbitmq_url:
                raise ValueError("Empty rabbitmq_url cluster node list")
            self._mq_nodes = rabbitmq_url
        else:
            raise ValueError("rabbitmq_url must be str or list of str")

        self._mq_url: str = None
        self._connection: aio_pika.RobustConnection = None
        self._channel: aio_pika.RobustChannel = None
        self._exchange: aio_pika.Exchange = None
        self._queues: Dict[str, aio_pika.Queue] = {}
        self._method_cache: Dict[str, callable] = {}

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            rabbitmq_url=crawler.settings.RABBITMQ_INFO.resolved_url,
            exchange_name=crawler.settings.RABBITMQ_INFO.EXCHANGE_NAME,
            exchange_type=crawler.settings.RABBITMQ_INFO.EXCHANGE_TYPE,
            prefetch_count=crawler.settings.RABBITMQ_INFO.PREFETCH_COUNT,
            persist=crawler.settings.SCHEDULER_PERSIST,
        )

    async def connect(self):
        self._mq_url = random.choice(self._mq_nodes)
        self._connection = await aio_pika.connect_robust(self._mq_url, loop=self.loop)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self.prefetch_count)
        self._exchange = await self._channel.declare_exchange(
            self.exchange_name, type=self.exchange_type, durable=self.persist
        )

    def __getattribute__(self, name: str):
        if name.startswith("_") or name in ("_method_cache", "connect", "close"):
            return super().__getattribute__(name)

        attr = super().__getattribute__(name)
        if not callable(attr) or not inspect.iscoroutinefunction(attr):
            return attr

        method_cache = super().__getattribute__("_method_cache")
        if name not in method_cache:
            @wraps(attr)
            async def wrapper(*args, **kwargs):
                if self.stop_event.is_set():
                    raise asyncio.CancelledError(f"Stop event set, abort RabbitMQ operation: {name}")
                try:
                    return await attr(*args, **kwargs)
                except (AMQPConnectionError, ChannelClosed):
                    await self.connect()
                    return await attr(*args, **kwargs)
            method_cache[name] = wrapper
        return method_cache[name]

    @auto_retry
    async def declare_queue(self, queue_name: str, routing_key: str = None):
        if queue_name in self._queues:
            return self._queues[queue_name]
        queue = await self._channel.declare_queue(
            queue_name, durable=self.persist, auto_delete=not self.persist
        )
        routing_key = routing_key or queue_name
        await queue.bind(self._exchange, routing_key=routing_key)
        self._queues[queue_name] = queue
        return queue

    @auto_retry
    async def rpush(self, queue_name: str, message: bytes, routing_key: str = None):
        if self.stop_event.is_set():
            raise asyncio.CancelledError("Stop event set, abort RabbitMQ push")
        if not self._exchange:
            await self.connect()
        routing_key = routing_key or queue_name
        async with self._lock:
            await self._exchange.publish(
                aio_pika.Message(
                    body=message,
                    delivery_mode=DeliveryMode.PERSISTENT if self.persist else None
                ),
                routing_key=routing_key
            )
        return True

    @auto_retry
    async def dequeue_request(self, queue_name: str, timeout: int = 30) -> Union[bytes, None]:
        """
        Channel closed by RPC timeout.

        ⚠️ Warning: Do NOT set this timeout too low. This is a design flaw in aio_pika.
        If the timeout triggers, the channel may be closed, which can crash the entire program.
        """
        if self.stop_event.is_set():
            raise asyncio.CancelledError("Stop event set, abort RabbitMQ pop")
        if not self._exchange:
            await self.connect()
        queue = await self.declare_queue(queue_name)
        try:
            async with self._lock:
                message: aio_pika.IncomingMessage = await asyncio.wait_for(
                    queue.get(timeout=timeout),
                    timeout=timeout
                )
                if message:
                    async with message.process():
                        return message.body
                return None
        except asyncio.TimeoutError:
            return None
        except QueueEmpty:
            return None

    @auto_retry
    async def llen(self, queue_name: str) -> int:
        queue = await self._channel.declare_queue(
            queue_name, durable=self.persist, passive=True
        )
        return queue.declaration_result.message_count

    async def close(self):
        self.stop_event.set()
        try:
            if self._channel and not self._channel.is_closed:
                await self._channel.close()
        except ChannelClosed:
            pass
        try:
            if self._connection and not self._connection.is_closed:
                await self._connection.close()
        except AMQPConnectionError:
            pass
