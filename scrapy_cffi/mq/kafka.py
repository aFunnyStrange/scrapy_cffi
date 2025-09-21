import asyncio
import inspect
import random
from functools import wraps
from typing import TYPE_CHECKING, Union, List, Dict, Optional

try:
    from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
    from aiokafka.admin import AIOKafkaAdminClient, NewTopic
    from aiokafka.errors import KafkaConnectionError
except ImportError as e:
    raise ImportError(
        "Missing aiokafka dependencies. "
        "Please install: pip install aiokafka"
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
        persistent_time: int = 24*60*60*7000
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
        self._consumers: Dict[str, AIOKafkaConsumer] = {}
        self._method_cache: Dict[str, callable] = {}

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            kafka_urls=crawler.settings.KAFKA_INFO.resolved_url,
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
    async def produce(
        self,
        topic: str,
        message: bytes,
        key: bytes = None,
        num_partitions: int = 1,
        replication_factor: int = 1,
    ):
        if self.stop_event.is_set():
            raise asyncio.CancelledError("Stop event set, abort Kafka produce")
        if self._producer is None:
            await self.connect()
        await self.ensure_topic(topic, num_partitions=num_partitions, replication_factor=replication_factor)
        await self._producer.send_and_wait(topic, message, key=key)

    @auto_retry
    async def consume(self, topic: str, timeout_ms: int = 1000) -> Optional[bytes]:
        if self.stop_event.is_set():
            raise asyncio.CancelledError("Stop event set, abort Kafka consume")
        if self._producer is None:
            await self.connect()
        await self.ensure_topic(topic)

        if topic not in self._consumers:
            consumer = AIOKafkaConsumer(
                topic,
                loop=self.loop,
                bootstrap_servers=self._bootstrap_servers,
                group_id=self.consumer_group,
                enable_auto_commit=True,
                auto_offset_reset="earliest",
            )
            await consumer.start()
            self._consumers[topic] = consumer
            await asyncio.sleep(1)  # 等 coordinator 就绪

        consumer = self._consumers[topic]

        try:
            msg = await asyncio.wait_for(consumer.getone(), timeout=timeout_ms / 1000)
            return msg.value
        except asyncio.TimeoutError:
            return None

    async def close(self):
        if self._producer:
            await self._producer.stop()
        await asyncio.gather(*[consumer.stop() for consumer in self._consumers.values()])