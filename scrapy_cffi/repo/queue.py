"""Implement transport-neutral request queues over RabbitMQ and Kafka clients."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, List, Optional

from ..service.resilience import ResourceSlot, RetryPolicy

if TYPE_CHECKING:
    from ..infra.kafka import KafkaClient
    from ..infra.rabbitmq import RabbitMQClient

from .contracts import QueueMessage


class RabbitMQQueueRepository:
    """Expose request queue semantics over RabbitMQ."""

    def __init__(
        self,
        slot: ResourceSlot[RabbitMQClient],
        retry_policy: RetryPolicy,
    ) -> None:
        """Bind RabbitMQ queue operations to a replaceable client."""
        self._slot = slot
        self._retry_policy = retry_policy

    @property
    def client(self) -> RabbitMQClient:
        """Return the active RabbitMQ client."""
        return self._slot.get()

    async def _run(self, operation: Any, allow_during_shutdown: bool = False) -> Any:
        """Execute one queue operation through the resilience service."""
        observed = {"generation": self._slot.generation}

        async def current_operation() -> Any:
            """Execute against and remember the active client generation."""
            observed["generation"] = self._slot.generation
            return await operation()

        return await self._retry_policy.run(
            current_operation,
            lambda: self._slot.replace(observed["generation"]),
            allow_during_shutdown=allow_during_shutdown,
        )

    async def push(
        self,
        queue_name: str,
        payload: bytes,
        key: Optional[bytes] = None,
    ) -> bool:
        """Publish one request payload."""
        del key
        return bool(await self._run(lambda: self.client.rpush(queue_name, payload)))

    async def pop(
        self,
        queue_name: str,
        consumer_group: Optional[str] = None,
        timeout: float = 30,
    ) -> Optional[bytes]:
        """Receive and settle one RabbitMQ request payload."""
        del consumer_group
        return await self._run(lambda: self.client.dequeue_request(queue_name, timeout=timeout))

    async def ack(self, message: Any) -> bool:
        """Report success because Basic.Get is settled during pop."""
        del message
        return True

    async def size(self, queue_name: str) -> int:
        """Return the external system's reported queue size."""
        return int(await self._run(lambda: self.client.llen(queue_name)))

    async def delete(self, queue_names: List[str]) -> None:
        """Delete framework-owned queues during shutdown."""
        for queue_name in sorted(set(queue_names)):
            await self._run(
                lambda name=queue_name: self.client.delete_queue(name),
                allow_during_shutdown=True,
            )


class KafkaQueueRepository:
    """Expose request queue and offset semantics over Kafka."""

    def __init__(
        self,
        slot: ResourceSlot[KafkaClient],
        retry_policy: RetryPolicy,
    ) -> None:
        """Bind Kafka operations to a replaceable client."""
        self._slot = slot
        self._retry_policy = retry_policy

    @property
    def client(self) -> KafkaClient:
        """Return the active Kafka client."""
        return self._slot.get()

    async def _run(self, operation: Any, allow_during_shutdown: bool = False) -> Any:
        """Execute one queue operation through the resilience service."""
        observed = {"generation": self._slot.generation}

        async def current_operation() -> Any:
            """Execute against and remember the active client generation."""
            observed["generation"] = self._slot.generation
            return await operation()

        return await self._retry_policy.run(
            current_operation,
            lambda: self._slot.replace(observed["generation"]),
            allow_during_shutdown=allow_during_shutdown,
        )

    async def push(
        self,
        queue_name: str,
        payload: bytes,
        key: Optional[bytes] = None,
    ) -> bool:
        """Publish one Kafka record."""
        result = await self._run(lambda: self.client.produce(queue_name, payload, key=key))
        return result is not None

    async def pop(
        self,
        queue_name: str,
        consumer_group: Optional[str] = None,
        timeout: float = 2.0,
    ) -> Optional[QueueMessage]:
        """Lease one Kafka record without committing its offset."""
        group = consumer_group or self.client.consumer_group
        record = await self._run(
            lambda: self.client.dequeue_request(queue_name, group, timeout=timeout)
        )
        if record is None:
            return None
        return QueueMessage(
            queue_name=record.topic,
            consumer_group=record.consumer_group,
            partition=record.partition,
            offset=record.offset,
            value=record.value,
        )

    async def ack(self, message: QueueMessage) -> bool:
        """Commit a completed Kafka delivery in contiguous offset order."""
        return bool(
            await self._run(
                lambda: self.client.ack_request(
                    message.queue_name,
                    message.consumer_group,
                    message.partition,
                    message.offset,
                )
            )
        )

    async def size(self, queue_name: str) -> int:
        """Return zero because Kafka lag requires a group-specific query."""
        del queue_name
        return 0

    async def delete(self, queue_names: List[str]) -> None:
        """Delete framework-owned topics during shutdown."""
        await self._run(
            lambda: self.client.delete_topics(queue_names),
            allow_during_shutdown=True,
        )

    async def ensure_topic(
        self,
        topic: str,
        num_partitions: int = 1,
        replication_factor: int = 1,
    ) -> None:
        """Ensure one explicitly requested Kafka topic exists."""
        await self._run(
            lambda: self.client.ensure_topic(
                topic,
                num_partitions=num_partitions,
                replication_factor=replication_factor,
            )
        )

    async def register_consumer(
        self,
        topic: str,
        callback: Callable[[bytes], None],
        consumer_group: Optional[str] = None,
        auto_offset_reset: str = "earliest",
    ) -> None:
        """Register a callback consumer on the active client generation."""
        await self._run(
            lambda: self.client.register_consumer(
                topic,
                callback,
                consumer_group=consumer_group,
                auto_offset_reset=auto_offset_reset,
            )
        )


__all__ = ["KafkaQueueRepository", "QueueMessage", "RabbitMQQueueRepository"]
