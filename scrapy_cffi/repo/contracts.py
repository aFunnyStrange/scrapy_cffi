"""Define storage and request-queue capabilities consumed by crawler services."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Union


@dataclass(frozen=True)
class QueueMessage:
    """Represent one leased request-queue delivery."""

    queue_name: str
    consumer_group: str
    partition: int
    offset: int
    value: bytes


class RedisRepositoryProtocol(Protocol):
    """Describe Redis semantics required by schedulers and deduplication."""

    redis_mode: str
    cluster_nodes: List[str]

    async def rpush(self, key: str, value: bytes) -> Any:
        """Append one value to a queue."""
        ...

    async def dequeue_request(self, queue_key: str, timeout: float = 2) -> Optional[bytes]:
        """Pop one queued request."""
        ...

    async def llen(self, key: str) -> int:
        """Return a queue length."""
        ...

    async def delete(self, key: str) -> int:
        """Delete one framework-owned key."""
        ...

    async def do_filter(self, fingerprint: str, key_new_seen: str, key_is_req: str) -> int:
        """Atomically test and record a request fingerprint."""
        ...

    async def do_bloom_filter(
        self,
        key_new_seen: str,
        key_is_req: str,
        index_list: List[int],
    ) -> int:
        """Atomically test and record Bloom-filter indices."""
        ...

    async def expire(self, key: str, seconds: int) -> Any:
        """Set key expiry."""
        ...

    async def sadd(self, key: str, value: Union[str, bytes]) -> Any:
        """Add a set member."""
        ...

    async def hset(self, key: str, field: str, value: bytes) -> Any:
        """Set a hash field."""
        ...

    async def hget(self, key: str, field: str) -> Optional[bytes]:
        """Read a hash field."""
        ...

    async def xadd(self, key: str, fields: Dict[Any, Any]) -> Any:
        """Append one stream entry."""
        ...

    def pipeline(self) -> Any:
        """Create one native Redis pipeline for an atomic batch."""
        ...

    async def dequeue_stream_request(
        self,
        stream_key: str,
        group_name: str,
        consumer_name: str,
        field: Optional[str] = "data",
        count: int = 1,
        block: int = 2000,
        group_start_id: str = "0",
        read_id: str = ">",
        mkstream: bool = True,
    ) -> Any:
        """Read one consumer-group stream delivery."""
        ...

    async def ack_stream_request(self, message: Any, group_name: str) -> int:
        """Acknowledge one stream delivery."""
        ...


class RequestQueueRepositoryProtocol(Protocol):
    """Describe transport-neutral request queue operations."""

    async def push(self, queue_name: str, payload: bytes, key: Optional[bytes] = None) -> bool:
        """Publish one request payload."""
        ...

    async def pop(self, queue_name: str, consumer_group: Optional[str] = None) -> Any:
        """Receive one request or delivery envelope."""
        ...

    async def ack(self, message: Any) -> Any:
        """Acknowledge one delivery when supported."""
        ...

    async def size(self, queue_name: str) -> int:
        """Return the approximate queue size."""
        ...

    async def delete(self, queue_names: List[str]) -> None:
        """Delete framework-owned transient queues or topics."""
        ...


__all__ = [
    "QueueMessage",
    "RedisRepositoryProtocol",
    "RequestQueueRepositoryProtocol",
]
