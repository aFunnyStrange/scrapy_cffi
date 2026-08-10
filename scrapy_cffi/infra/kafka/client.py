"""Implement one-shot Kafka connectivity and record operations."""

import asyncio
import inspect
import ssl
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Union, List, Dict, Optional, Callable, Tuple

try:
    from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
    from aiokafka.admin import AIOKafkaAdminClient, NewTopic
    from aiokafka.errors import KafkaConnectionError, TopicAlreadyExistsError
    from aiokafka.structs import OffsetAndMetadata, TopicPartition
except ImportError as e:
    raise ImportError(
        "Missing aiokafka dependencies. Please install: pip install aiokafka"
    ) from e

if TYPE_CHECKING:
    from ...config.queue import KafkaInfo


@dataclass(frozen=True)
class KafkaRecord:
    """Represent one leased Kafka record and its acknowledgement coordinates."""
    topic: str
    consumer_group: str
    partition: int
    offset: int
    value: bytes

class KafkaClient:
    """Own one generation of Kafka producer and consumer connections."""

    def __init__(
        self,
        kafka_url: Optional[Union[str, List[str]]] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        consumer_group: str = "scrapy_cffi",
        persistent_time: int = 7*24*60*60*1000,
        num_partitions: int = 3,
        replication_factor: int = 1,
        auto_offset_reset: str = "earliest",
        client_id: str = "scrapy_cffi",
        request_timeout_ms: int = 40000,
        security_protocol: str = "PLAINTEXT",
        sasl_mechanism: Optional[str] = None,
        sasl_username: Optional[str] = None,
        sasl_password: Optional[str] = None,
        ssl_cafile: Optional[str] = None,
        ssl_certfile: Optional[str] = None,
        ssl_keyfile: Optional[str] = None,
    ):
        """Configure one-shot Kafka connectivity without retry policy."""
        if loop is not None:
            self.loop = loop
        else:
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                self.loop = None
        self.consumer_group = consumer_group
        self.persistent_time = persistent_time
        self.num_partitions = num_partitions
        self.replication_factor = replication_factor
        self.auto_offset_reset = auto_offset_reset
        self._client_kwargs = {
            "client_id": client_id,
            "request_timeout_ms": request_timeout_ms,
            "security_protocol": security_protocol,
        }
        if sasl_mechanism:
            self._client_kwargs.update(
                sasl_mechanism=sasl_mechanism,
                sasl_plain_username=sasl_username,
                sasl_plain_password=sasl_password,
            )
        if security_protocol.upper() in {"SSL", "SASL_SSL"}:
            ssl_context = ssl.create_default_context(cafile=ssl_cafile)
            if ssl_certfile:
                ssl_context.load_cert_chain(ssl_certfile, keyfile=ssl_keyfile)
            self._client_kwargs["ssl_context"] = ssl_context

        if isinstance(kafka_url, str):
            self.topology = "single"
            self._nodes = [kafka_url]
        elif isinstance(kafka_url, list):
            self.topology = "cluster"
            if not kafka_url:
                raise ValueError("Empty Kafka cluster node list")
            self._nodes = kafka_url
        else:
            raise ValueError("kafka_url must be str or list of str")

        self._bootstrap_servers: Any = None
        self._producer: Any = None
        self._connect_lock = asyncio.Lock()
        self._consumers: Dict[Tuple[str, str], Any] = {}
        self._consumer_tasks: List[asyncio.Task] = []
        self._callbacks: Dict[Tuple[str, str], Callable[[bytes], Any]] = {}
        self._callback_resets: Dict[Tuple[str, str], str] = {}
        self._consumer_locks: Dict[Tuple[str, str], asyncio.Lock] = {}
        self._consumer_create_lock = asyncio.Lock()
        self._offset_lock = asyncio.Lock()
        self._pending_offsets = {}
        self._ensured_topics = set()
        self._topic_lock = asyncio.Lock()
    @classmethod
    def from_info(cls, info: "KafkaInfo") -> "KafkaClient":
        """Build a Kafka client from validated framework settings."""
        if not info.resolved_url:
            raise ValueError("KafkaClient requires a configured URL or cluster nodes")
        return cls(
            kafka_url=info.resolved_url,
            consumer_group=info.CONSUMER_GROUP,
            persistent_time=info.PERSISTENT_TIME,
            num_partitions=info.NUM_PARTITIONS,
            replication_factor=info.REPLICATION_FACTOR or 1,
            auto_offset_reset=info.AUTO_OFFSET_RESET,
            client_id=info.CLIENT_ID,
            request_timeout_ms=info.REQUEST_TIMEOUT_MS,
            security_protocol=info.SECURITY_PROTOCOL,
            sasl_mechanism=info.SASL_MECHANISM,
            sasl_username=info.SASL_USERNAME,
            sasl_password=info.SASL_PASSWORD,
            ssl_cafile=info.SSL_CAFILE,
            ssl_certfile=info.SSL_CERTFILE,
            ssl_keyfile=info.SSL_KEYFILE,
        )

    async def connect(self) -> None:
        """Start this client generation once."""
        async with self._connect_lock:
            await self._connect_transport()

    async def _connect_transport(self) -> None:
        """Create and start the underlying producer transport."""
        if self._producer is not None:
            return
        if self.loop is None:
            self.loop = asyncio.get_running_loop()
        self._bootstrap_servers = (
            self._nodes[0] if self.topology == "single" else self._nodes
        )
        self._producer = AIOKafkaProducer(
            loop=self.loop,
            bootstrap_servers=self._bootstrap_servers,
            **self._client_kwargs,
        )
        try:
            await self._producer.start()
        except BaseException:
            self._producer = None
            raise

    async def ensure_topic(
        self,
        topic: str,
        num_partitions: int = 1,
        replication_factor: int = 1,
    ) -> None:
        """Create a topic when absent and wait until its partitions are ready."""
        if topic in self._ensured_topics:
            return
        producer = self._producer
        if producer is None:
            await self.connect()
            producer = self._producer
        if producer is None:
            raise RuntimeError("KafkaClient did not start its producer")
        admin = AIOKafkaAdminClient(
            bootstrap_servers=self._bootstrap_servers,
            loop=self.loop,
            **self._client_kwargs,
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
                try:
                    await admin.create_topics([new_topic])
                except TopicAlreadyExistsError:
                    # Another worker may create the shared topic after our
                    # list_topics call and before create_topics.
                    pass
            await self._wait_topic_ready(
                admin,
                topic,
                num_partitions=num_partitions,
                replication_factor=replication_factor,
            )
            self._ensured_topics.add(topic)
        finally:
            await admin.close()

    async def _wait_topic_ready(
        self,
        admin: AIOKafkaAdminClient,
        topic: str,
        num_partitions: int,
        replication_factor: int,
    ) -> None:
        """Wait until a newly-created replicated topic is actually usable."""
        loop = self.loop or asyncio.get_running_loop()
        deadline = loop.time() + max(5.0, self._client_kwargs["request_timeout_ms"] / 1000)
        while loop.time() < deadline:
            descriptions = await admin.describe_topics([topic])
            description = next(
                (item for item in descriptions if item.get("topic") == topic),
                None,
            )
            partitions = description.get("partitions", []) if description else []
            ready = (
                description is not None
                and description.get("error_code", 0) == 0
                and len(partitions) >= num_partitions
                and all(
                    partition.get("leader", -1) >= 0
                    and partition.get("leader") in partition.get("isr", [])
                    and len(partition.get("replicas", [])) >= replication_factor
                    for partition in partitions
                )
            )
            if ready:
                return
            await asyncio.sleep(0.2)
        raise KafkaConnectionError(
            "Kafka topic %r was created but its partitions did not become ready" % topic
        )

    async def produce(
        self,
        topic: str,
        message: bytes,
        key: Optional[bytes] = None,
    ) -> Any:
        """Publish and await acknowledgement for one record."""
        producer = self._producer
        if producer is None:
            await self.connect()
            producer = self._producer
        if producer is None:
            raise RuntimeError("KafkaClient did not start its producer")
        if topic not in self._ensured_topics:
            async with self._topic_lock:
                await self.ensure_topic(
                    topic,
                    num_partitions=self.num_partitions,
                    replication_factor=self.replication_factor,
                )
        res = await producer.send_and_wait(topic, message, key=key)
        return res

    async def produce_async(
        self,
        topic: str,
        message: bytes,
        key: Optional[bytes] = None,
    ) -> None:
        """Submit one record through the vendor's asynchronous send API."""
        producer = self._producer
        if producer is None:
            await self.connect()
            producer = self._producer
        if producer is None:
            raise RuntimeError("KafkaClient did not start its producer")
        result = producer.send(topic, message, key=key)
        if inspect.iscoroutine(result):
            await result
        else:
            await asyncio.to_thread(lambda: result)

    async def ensure_topics(self, topics: List[str]) -> None:
        """Ensure each requested topic exists."""
        for t in topics:
            await self.ensure_topic(t)

    async def _get_request_consumer(
        self,
        topic: str,
        consumer_group: str,
        auto_offset_reset: Optional[str] = None,
    ) -> Any:
        """Return or create the manual-commit consumer for a topic and group."""
        key = (topic, consumer_group)
        async with self._consumer_create_lock:
            consumer = self._consumers.get(key)
            if consumer is not None:
                return consumer
            if self._producer is None:
                await self.connect()
            if topic not in self._ensured_topics:
                async with self._topic_lock:
                    await self.ensure_topic(
                        topic,
                        num_partitions=self.num_partitions,
                        replication_factor=self.replication_factor,
                    )
            consumer = AIOKafkaConsumer(
                topic,
                loop=self.loop,
                bootstrap_servers=self._bootstrap_servers,
                group_id=consumer_group,
                enable_auto_commit=False,
                auto_offset_reset=auto_offset_reset or self.auto_offset_reset,
                **self._client_kwargs,
            )
            await consumer.start()
            self._consumers[key] = consumer
            self._consumer_locks[key] = asyncio.Lock()
            return consumer

    async def dequeue_request(
        self,
        topic: str,
        consumer_group: str,
        timeout: float = 2.0,
        auto_offset_reset: Optional[str] = None,
    ) -> Optional[KafkaRecord]:
        """Lease one record; its offset is committed only by ``ack_request``."""
        consumer = await self._get_request_consumer(topic, consumer_group, auto_offset_reset)
        async with self._consumer_locks[(topic, consumer_group)]:
            try:
                record = await asyncio.wait_for(consumer.getone(), timeout=timeout)
            except asyncio.TimeoutError:
                return None
            # Record the lease before another scheduler loop can fetch the next
            # offset, preserving partition order in the pending deque.
            pending_key = (topic, consumer_group, record.partition)
            async with self._offset_lock:
                pending = self._pending_offsets.setdefault(pending_key, deque())
                pending.append([record.offset, False])
        return KafkaRecord(
            topic=topic,
            consumer_group=consumer_group,
            partition=record.partition,
            offset=record.offset,
            value=record.value,
        )

    async def ack_request(
        self,
        topic: str,
        consumer_group: str,
        partition: int,
        offset: int,
    ) -> bool:
        """Commit the highest contiguous completed offset for a partition."""
        pending_key = (
            topic,
            consumer_group,
            partition,
        )
        consumer = self._consumers.get((topic, consumer_group))
        if consumer is None:
            return False

        async with self._offset_lock:
            pending = self._pending_offsets.get(pending_key)
            if not pending:
                return False
            for entry in pending:
                if entry[0] == offset:
                    entry[1] = True
                    break
            else:
                return False

            commit_offset = None
            while pending and pending[0][1]:
                commit_offset = pending.popleft()[0] + 1
            if not pending:
                self._pending_offsets.pop(pending_key, None)
            if commit_offset is None:
                return True

            tp = TopicPartition(topic, partition)
            await consumer.commit({tp: OffsetAndMetadata(commit_offset, "")})
            return True

    async def _consume_loop(self, topic: str, consumer_group: str) -> None:
        """Dispatch callback-consumer records until cancellation or disconnect."""
        key = (topic, consumer_group)
        consumer = self._consumers[key]
        callback = self._callbacks[key]

        try:
            while True:
                try:
                    msg = await asyncio.wait_for(consumer.getone(), timeout=1.0)
                    if inspect.iscoroutinefunction(callback):
                        await callback(msg.value)
                    else:
                        callback(msg.value)
                except asyncio.TimeoutError:
                    continue
                except KafkaConnectionError:
                    return
        except asyncio.CancelledError:
            pass

    async def register_consumer(
        self,
        topic: str,
        callback: Callable[[bytes], Any],
        consumer_group: Optional[str] = None,
        auto_offset_reset: str = "earliest"
    ) -> None:
        """Register one callback consumer if the topic/group is not active."""
        consumer_group = consumer_group or self.consumer_group
        key = (topic, consumer_group)

        if key not in self._consumers:
            await self._start_callback_consumer(
                topic,
                callback,
                consumer_group,
                auto_offset_reset,
            )

    async def _start_callback_consumer(
        self,
        topic: str,
        callback: Callable[[bytes], Any],
        consumer_group: str,
        auto_offset_reset: str,
    ) -> None:
        """Start the vendor callback consumer for one topic and group."""
        if self._producer is None:
            await self.connect()
        consumer = AIOKafkaConsumer(
            topic,
            loop=self.loop,
            bootstrap_servers=self._bootstrap_servers,
            group_id=consumer_group,
            enable_auto_commit=True,
            auto_offset_reset=auto_offset_reset,
            **self._client_kwargs,
        )
        await consumer.start()
        key = (topic, consumer_group)
        self._consumers[key] = consumer
        self._callbacks[key] = callback
        self._callback_resets[key] = auto_offset_reset
        loop = self.loop or asyncio.get_running_loop()
        self.loop = loop
        task = loop.create_task(self._consume_loop(topic, consumer_group))
        self._consumer_tasks.append(task)

    async def delete_topics(self, topics: List[str]) -> None:
        """Delete framework-owned transient topics, including during shutdown."""
        names = sorted(set(topics))
        if not names:
            return
        if self._producer is None:
            await self.connect()

        consumers = [
            (key, consumer)
            for key, consumer in self._consumers.items()
            if key[0] in names
        ]
        if consumers:
            await asyncio.gather(
                *[consumer.stop() for _, consumer in consumers],
                return_exceptions=True,
            )
            for key, _ in consumers:
                self._consumers.pop(key, None)
                self._callbacks.pop(key, None)
                self._callback_resets.pop(key, None)
                self._consumer_locks.pop(key, None)
            async with self._offset_lock:
                for key in list(self._pending_offsets):
                    if key[0] in names:
                        self._pending_offsets.pop(key, None)

        admin = AIOKafkaAdminClient(
            bootstrap_servers=self._bootstrap_servers,
            loop=self.loop,
            **self._client_kwargs,
        )
        await admin.start()
        try:
            existing = await admin.list_topics()
            removable = [name for name in names if name in existing]
            if removable:
                await admin.delete_topics(removable)
            self._ensured_topics.difference_update(names)
        finally:
            await admin.close()

    async def close(self) -> None:
        """Close all transports owned by this client generation."""
        async with self._connect_lock:
            await self._close_transport(clear_callbacks=True)

    async def _close_transport(self, clear_callbacks: bool) -> None:
        """Stop consumers, callbacks, and the producer transport."""
        current_task = asyncio.current_task()
        tasks_to_wait = []
        for task in self._consumer_tasks:
            if task is current_task:
                continue
            task.cancel()
            tasks_to_wait.append(task)
        await asyncio.gather(*tasks_to_wait, return_exceptions=True)
        self._consumer_tasks.clear()

        await asyncio.gather(*[c.stop() for c in self._consumers.values()], return_exceptions=True)
        self._consumers.clear()
        if clear_callbacks:
            self._callbacks.clear()
            self._callback_resets.clear()
        self._consumer_locks.clear()
        self._pending_offsets.clear()

        if self._producer:
            await self._producer.stop()
            self._producer = None


__all__ = ["KafkaClient", "KafkaRecord"]
