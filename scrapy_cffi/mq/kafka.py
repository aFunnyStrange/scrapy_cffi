import asyncio
import inspect
import random
from functools import wraps
from typing import TYPE_CHECKING, Union, List, Dict, Optional, Callable, Tuple

try:
    from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
    from aiokafka.admin import AIOKafkaAdminClient, NewTopic
    from aiokafka.errors import KafkaConnectionError
except ImportError as e:
    raise ImportError(
        "Missing aiokafka dependencies. Please install: pip install aiokafka"
    ) from e

from tenacity import retry, wait_fixed, retry_if_exception_type

if TYPE_CHECKING:
    from ..crawler import Crawler

def auto_retry(func):
    @wraps(func)
    @retry(
        wait=wait_fixed(1),
        retry=retry_if_exception_type(KafkaConnectionError),
        reraise=True
    )
    async def wrapper(self, *args, **kwargs):
        if self.stop_event.is_set():
            raise asyncio.CancelledError("Stop event set, abort Kafka operation")
        try:
            return await func(self, *args, **kwargs)
        except KafkaConnectionError:
            if self.stop_event.is_set():
                raise asyncio.CancelledError("Stop event set during reconnect")
            await self.connect()
            return await func(self, *args, **kwargs)
    return wrapper

class KafkaManager:
    def __init__(
        self,
        stop_event: asyncio.Event = None,
        kafka_url: Union[str, List[str]] = None,
        loop: asyncio.AbstractEventLoop = None,
        consumer_group: str = "scrapy_cffi",
        persistent_time: int = 7*24*60*60*1000
    ):
        self.stop_event = stop_event or asyncio.Event()
        self.loop = loop or asyncio.get_event_loop()
        self.consumer_group = consumer_group
        self.persistent_time = persistent_time

        if isinstance(kafka_url, str):
            self.mq_mode = "single"
            self._nodes = [kafka_url]
        elif isinstance(kafka_url, list):
            self.mq_mode = "cluster"
            if not kafka_url:
                raise ValueError("Empty Kafka cluster node list")
            self._nodes = kafka_url
        else:
            raise ValueError("kafka_url must be str or list of str")

        self._bootstrap_servers: str = None
        self._producer: Optional[AIOKafkaProducer] = None
        self._consumers: Dict[Tuple[str, str], AIOKafkaConsumer] = {}
        self._consumer_tasks: List[asyncio.Task] = []
        self._callbacks: Dict[Tuple[str, str], Callable[[bytes], None]] = {}
        self._method_cache: Dict[str, callable] = {}

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            kafka_url=crawler.settings.KAFKA_INFO.resolved_url,
            consumer_group=crawler.settings.KAFKA_INFO.CONSUMER_GROUP,
            persistent_time=crawler.settings.KAFKA_INFO.PERSISTENT_TIME,
        )

    @auto_retry
    async def connect(self):
        self._bootstrap_servers = random.choice(self._nodes)
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                loop=self.loop,
                bootstrap_servers=self._bootstrap_servers,
            )
            await self._producer.start()

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
                    raise asyncio.CancelledError(f"Stop event set, abort Kafka operation: {name}")
                try:
                    return await attr(*args, **kwargs)
                except KafkaConnectionError:
                    await self.connect()
                    return await attr(*args, **kwargs)
            method_cache[name] = wrapper
        return method_cache[name]

    @auto_retry
    async def ensure_topic(self, topic: str, num_partitions: int = 1, replication_factor: int = 1):
        admin = AIOKafkaAdminClient(
            bootstrap_servers=self._bootstrap_servers,
            loop=self.loop
        )
        await admin.start()
        try:
            existing = await admin.list_topics()
            if topic not in existing:
                new_topic = NewTopic(
                    name=topic,
                    num_partitions=num_partitions,
                    replication_factor=replication_factor,
                    topic_configs={
                        "retention.ms": str(self.persistent_time),
                        "cleanup.policy": "delete"
                    }
                )
                await admin.create_topics([new_topic])
        finally:
            await admin.close()

    @auto_retry
    async def produce(self, topic: str, message: bytes, key: bytes = None):
        if self.stop_event.is_set():
            raise asyncio.CancelledError("Stop event set, abort Kafka produce")
        if self._producer is None:
            await self.connect()
        res = await self._producer.send_and_wait(topic, message, key=key)
        return res

    async def produce_async(self, topic: str, message: bytes, key: bytes = None):
        if self.stop_event.is_set():
            return
        if self._producer is None:
            await self.connect()
        self._producer.send(topic, message, key=key)

    async def ensure_topics(self, topics: List[str]):
        for t in topics:
            await self.ensure_topic(t)

    @auto_retry
    async def _consume_loop(self, topic: str, consumer_group: str):
        key = (topic, consumer_group)
        consumer = self._consumers[key]
        callback = self._callbacks[key]

        try:
            while not self.stop_event.is_set():
                try:
                    msg = await asyncio.wait_for(consumer.getone(), timeout=1.0)
                    if inspect.iscoroutinefunction(callback):
                        await callback(msg.value)
                    else:
                        callback(msg.value)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass

    @auto_retry
    async def register_consumer(
        self,
        topic: str,
        callback: Callable[[bytes], None],
        consumer_group: Optional[str] = None,
        auto_offset_reset: str = "earliest"
    ):
        consumer_group = consumer_group or self.consumer_group
        key = (topic, consumer_group)

        if key not in self._consumers:
            if self._producer is None:
                await self.connect()
            consumer = AIOKafkaConsumer(
                topic,
                loop=self.loop,
                bootstrap_servers=self._bootstrap_servers,
                group_id=consumer_group,
                enable_auto_commit=True,
                auto_offset_reset=auto_offset_reset
            )
            await consumer.start()
            self._consumers[key] = consumer
            self._callbacks[key] = callback

            task = self.loop.create_task(self._consume_loop(topic, consumer_group))
            self._consumer_tasks.append(task)

    async def close(self):
        for task in self._consumer_tasks:
            task.cancel()
        await asyncio.gather(*self._consumer_tasks, return_exceptions=True)

        await asyncio.gather(*[c.stop() for c in self._consumers.values()], return_exceptions=True)
        self._consumers.clear()
        self._callbacks.clear()

        if self._producer:
            await self._producer.stop()