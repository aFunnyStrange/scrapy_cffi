import asyncio
import random
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

from ..utils.reconnect import AsyncReconnectController, reconnectable

if TYPE_CHECKING:
    from ..crawler import Crawler
    from ..models.mq import RabbitMQInfo

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
        connection_timeout: float = 10.0,
        heartbeat: int = 60,
    ):
        self.stop_event = stop_event or asyncio.Event()
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type
        self.prefetch_count = prefetch_count
        self.persist = persist
        self.connection_timeout = connection_timeout
        self.heartbeat = heartbeat
        self.loop = loop or asyncio.get_running_loop()
        self._lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()

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
        self._reconnect_controller = AsyncReconnectController(
            self.stop_event,
            self._reconnect,
            (AMQPConnectionError, ChannelClosed),
            label="RabbitMQ",
        )

    @classmethod
    def from_rabbitmq_info(
        cls,
        stop_event: asyncio.Event,
        info: "RabbitMQInfo",
        *,
        persist: bool = False,
    ):
        if not info.resolved_url:
            raise ValueError("RabbitMQManager.from_rabbitmq_info requires RABBITMQ_INFO URL or cluster nodes")
        exchange_type = info.EXCHANGE_TYPE
        if isinstance(exchange_type, str):
            exchange_type = ExchangeType(exchange_type)
        return cls(
            stop_event=stop_event,
            rabbitmq_url=info.resolved_url,
            exchange_name=info.EXCHANGE_NAME,
            exchange_type=exchange_type,
            prefetch_count=info.PREFETCH_COUNT,
            persist=persist,
            connection_timeout=info.CONNECTION_TIMEOUT,
            heartbeat=info.HEARTBEAT,
        )

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls.from_rabbitmq_info(
            crawler.stop_event,
            crawler.settings.RABBITMQ_INFO,
            persist=crawler.settings.SCHEDULER_PERSIST,
        )

    async def connect(self):
        async with self._connect_lock:
            await self._connect_transport()

    async def _connect_transport(self):
        if (
            self._connection is not None
            and not self._connection.is_closed
            and self._channel is not None
            and not self._channel.is_closed
            and self._exchange is not None
        ):
            return
        last_exc = None
        for attempt in range(3):
            for node_url in random.sample(self._mq_nodes, k=len(self._mq_nodes)):
                try:
                    self._mq_url = node_url
                    self._connection = await aio_pika.connect_robust(
                        self._mq_url,
                        loop=self.loop,
                        timeout=self.connection_timeout,
                        heartbeat=self.heartbeat,
                    )
                    self._channel = await self._connection.channel()
                    await self._channel.set_qos(prefetch_count=self.prefetch_count)
                    self._exchange = await self._channel.declare_exchange(
                        # Exchange durability must not vary with scheduler state:
                        # persistent and transient spiders may share one exchange.
                        # Queue/message durability still follows SCHEDULER_PERSIST.
                        self.exchange_name,
                        type=self.exchange_type,
                        durable=True,
                    )
                    # Queue objects belong to the old channel.
                    self._queues.clear()
                    return
                except (AMQPConnectionError, ChannelClosed) as exc:
                    last_exc = exc
                    self._connection = None
                    self._channel = None
                    self._exchange = None
            if attempt < 2 and not self.stop_event.is_set():
                await asyncio.sleep(1)
        if last_exc:
            raise last_exc

    async def _reconnect(self):
        async with self._connect_lock:
            await self._close_transport()
            await self._connect_transport()

    @reconnectable
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

    @reconnectable
    async def rpush(self, queue_name: str, message: bytes, routing_key: str = None):
        if self.stop_event.is_set():
            raise asyncio.CancelledError("Stop event set, abort RabbitMQ push")
        if not self._exchange:
            await self.connect()
        routing_key = routing_key or queue_name
        # Binds the queue to the exchange before publishing; otherwise the broker drops
        # messages when no queue is bound yet (e.g. first scheduled request before any consumer).
        await self.declare_queue(queue_name, routing_key=routing_key)
        async with self._lock:
            await self._exchange.publish(
                aio_pika.Message(
                    body=message,
                    delivery_mode=DeliveryMode.PERSISTENT if self.persist else None
                ),
                routing_key=routing_key
            )
        return True

    @reconnectable
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
            # NOTE:
            # queue.get() can wait for a long time on empty queues.
            # If we hold the manager-wide lock here, one empty queue can block
            # all other spider queues (push/pop) in run_all_spiders mode.
            # Keep publish serialized, but do not serialize long-lived dequeue waits.
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

    @reconnectable
    async def llen(self, queue_name: str) -> int:
        try:
            queue = await self._channel.declare_queue(
                queue_name, durable=self.persist, passive=True
            )
            return queue.declaration_result.message_count
        except aio_pika.exceptions.ChannelClosed:
            await self.connect()
            return 0
        except aio_pika.exceptions.ChannelInvalidStateError:
            return 0

    async def delete_queue(self, queue_name: str) -> bool:
        """Delete framework-owned transient state, including during shutdown."""
        if not self._channel or self._channel.is_closed:
            await self.connect()
        self._queues.pop(queue_name, None)
        try:
            await self._channel.queue_delete(
                queue_name,
                if_unused=False,
                if_empty=False,
            )
        except ChannelClosed as exc:
            if getattr(exc, "reply_code", None) == 404 or "NOT_FOUND" in str(exc):
                return False
            raise
        return True

    async def close(self):
        async with self._connect_lock:
            await self._close_transport()

    async def _close_transport(self):
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
        finally:
            self._connection = None
            self._channel = None
            self._exchange = None
            self._queues.clear()
