"""Implement one-shot RabbitMQ connectivity and channel operations."""

import asyncio
import random
from typing import TYPE_CHECKING, Any, Union, List, Dict, Optional

try:
    import aio_pika
    from aio_pika import ExchangeType, DeliveryMode
    from aio_pika.exceptions import AMQPConnectionError, ChannelClosed, QueueEmpty
except ImportError as e:
    raise ImportError(
        "Missing aio_pika dependencies. "
        "Please install: pip install aio_pika"
    ) from e

if TYPE_CHECKING:
    from ...config.queue import RabbitMQInfo

class RabbitMQClient:
    """Own one generation of RabbitMQ connection and channel state."""

    def __init__(
        self,
        rabbitmq_url: Optional[Union[str, List[str]]] = None,
        exchange_name: str = "scrapy_cffi",
        exchange_type: ExchangeType = ExchangeType.DIRECT,
        prefetch_count: int = 10,
        persist: bool = False,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        connection_timeout: float = 10.0,
        heartbeat: int = 60,
    ):
        """Configure one-shot RabbitMQ connectivity without retry policy."""
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
            self.topology = "single"
            self._mq_nodes = [rabbitmq_url]
        elif isinstance(rabbitmq_url, list):
            self.topology = "cluster"
            if not rabbitmq_url:
                raise ValueError("Empty rabbitmq_url cluster node list")
            self._mq_nodes = rabbitmq_url
        else:
            raise ValueError("rabbitmq_url must be str or list of str")

        self._mq_url: Optional[str] = None
        self._connection: Any = None
        self._channel: Any = None
        self._exchange: Any = None
        self._queues: Dict[str, Any] = {}
        self._consumer_channels: Dict[str, Any] = {}
        self._consumer_queues: Dict[str, Any] = {}
        self._consumer_lock = asyncio.Lock()
    @classmethod
    def from_info(
        cls,
        info: "RabbitMQInfo",
        *,
        persist: bool = False,
    ) -> "RabbitMQClient":
        """Build a RabbitMQ client from validated framework settings."""
        if not info.resolved_url:
            raise ValueError("RabbitMQClient requires a configured URL or cluster nodes")
        exchange_type = info.EXCHANGE_TYPE
        if isinstance(exchange_type, str):
            exchange_type = ExchangeType(exchange_type)
        return cls(
            rabbitmq_url=info.resolved_url,
            exchange_name=info.EXCHANGE_NAME,
            exchange_type=exchange_type,
            prefetch_count=info.PREFETCH_COUNT,
            persist=persist,
            connection_timeout=info.CONNECTION_TIMEOUT,
            heartbeat=info.HEARTBEAT,
        )

    async def connect(self) -> None:
        """Start this client generation once."""
        async with self._connect_lock:
            await self._connect_transport()

    async def _connect_transport(self) -> None:
        """Open the connection, channel, exchange, and QoS state."""
        if (
            self._connection is not None
            and not self._connection.is_closed
            and self._channel is not None
            and not self._channel.is_closed
            and self._exchange is not None
        ):
            return
        self._mq_url = random.choice(self._mq_nodes)
        self._connection = await aio_pika.connect(
            self._mq_url,
            loop=self.loop,
            timeout=self.connection_timeout,
            heartbeat=self.heartbeat,
        )
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self.prefetch_count)
        self._exchange = await self._channel.declare_exchange(
            self.exchange_name,
            type=self.exchange_type,
            durable=True,
        )
        self._queues.clear()
        self._consumer_channels.clear()
        self._consumer_queues.clear()

    async def declare_queue(self, queue_name: str, routing_key: Optional[str] = None) -> Any:
        """Declare and bind a durable logical request queue."""
        async with self._lock:
            return await self._declare_queue_unlocked(queue_name, routing_key)

    async def _declare_queue_unlocked(self, queue_name: str, routing_key: Optional[str] = None) -> Any:
        """Declare one queue while the caller owns the declaration lock."""
        if queue_name in self._queues:
            return self._queues[queue_name]
        queue = await self._channel.declare_queue(
            # Queue identity must remain stable when persistent and transient
            # crawlers (or an external ingress publisher) share a name.
            # SCHEDULER_PERSIST controls message delivery mode and framework
            # cleanup, not RabbitMQ entity declaration arguments.
            queue_name,
            durable=True,
            auto_delete=False,
        )
        routing_key = routing_key or queue_name
        await queue.bind(self._exchange, routing_key=routing_key)
        self._queues[queue_name] = queue
        return queue

    async def rpush(
        self,
        queue_name: str,
        message: bytes,
        routing_key: Optional[str] = None,
    ) -> bool:
        """Publish one request payload after ensuring its binding exists."""
        if not self._exchange:
            await self.connect()
        routing_key = routing_key or queue_name
        # Binds the queue to the exchange before publishing; otherwise the broker drops
        # messages when no queue is bound yet (e.g. first scheduled request before any consumer).
        async with self._lock:
            await self._declare_queue_unlocked(queue_name, routing_key=routing_key)
            await self._exchange.publish(
                aio_pika.Message(
                    body=message,
                    delivery_mode=DeliveryMode.PERSISTENT if self.persist else None
                ),
                routing_key=routing_key
            )
        return True

    async def dequeue_request(self, queue_name: str, timeout: float = 30) -> Optional[bytes]:
        """
        Cancellation-safe short polling for aio-pika's ``Basic.Get`` RPC.

        Polls are capped at one second so Ctrl+C remains responsive.
        The underlying RPC is shielded and settled before shutdown closes the channel.
        """
        if not self._exchange:
            await self.connect()
        poll_timeout = min(max(float(timeout), 0.1), 1.0)
        queue = await self._get_consumer_queue(queue_name)
        get_task = asyncio.create_task(
            queue.get(timeout=poll_timeout, fail=False)
        )
        try:
            # Every logical queue owns a channel, so start/work Basic.Get RPCs
            # cannot block publishing or one another.
            message = await asyncio.shield(get_task)
            if message:
                async with message.process():
                    return message.body
            return None
        except asyncio.CancelledError:
            try:
                message = await get_task
                if message is not None:
                    await message.reject(requeue=True)
            except (asyncio.TimeoutError, QueueEmpty, ChannelClosed):
                pass
            raise
        except (asyncio.TimeoutError, QueueEmpty):
            return None

    async def _get_consumer_queue(self, queue_name: str) -> Any:
        """Return a queue backed by a dedicated consumer channel."""
        queue = self._consumer_queues.get(queue_name)
        if queue is not None:
            return queue
        async with self._consumer_lock:
            queue = self._consumer_queues.get(queue_name)
            if queue is not None:
                return queue
            channel = await self._connection.channel()
            await channel.set_qos(prefetch_count=self.prefetch_count)
            exchange = await channel.declare_exchange(
                self.exchange_name,
                type=self.exchange_type,
                durable=True,
            )
            queue = await channel.declare_queue(
                queue_name,
                durable=True,
                auto_delete=False,
            )
            await queue.bind(exchange, routing_key=queue_name)
            self._consumer_channels[queue_name] = channel
            self._consumer_queues[queue_name] = queue
            return queue

    async def llen(self, queue_name: str) -> int:
        """Return the broker-reported message count for one queue."""
        async with self._lock:
            queue = await self._channel.declare_queue(
                queue_name, durable=True, auto_delete=False, passive=True
            )
            return int(queue.declaration_result.message_count or 0)

    async def delete_queue(self, queue_name: str) -> bool:
        """Delete framework-owned transient state, including during shutdown."""
        if not self._channel or self._channel.is_closed:
            await self.connect()
        self._queues.pop(queue_name, None)
        self._consumer_queues.pop(queue_name, None)
        consumer_channel = self._consumer_channels.pop(queue_name, None)
        if consumer_channel is not None and not consumer_channel.is_closed:
            await consumer_channel.close()
        try:
            async with self._lock:
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

    async def close(self) -> None:
        """Close all transports owned by this client generation."""
        async with self._connect_lock:
            await self._close_transport()

    async def _close_transport(self) -> None:
        """Close consumer channels, the shared channel, and connection."""
        consumer_channels = list(self._consumer_channels.values())
        self._consumer_channels.clear()
        self._consumer_queues.clear()
        if consumer_channels:
            await asyncio.gather(
                *[
                    channel.close()
                    for channel in consumer_channels
                    if not channel.is_closed
                ],
                return_exceptions=True,
            )
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
