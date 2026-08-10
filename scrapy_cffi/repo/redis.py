"""Implement crawler Redis semantics over a replaceable Redis transport."""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from ..infra.redis import RedisClient
from ..service.resilience import ResourceSlot, RetryPolicy


@dataclass(frozen=True)
class RedisStreamMessage:
    """Represent one Redis Stream delivery."""

    stream_key: str
    message_id: Union[str, bytes]
    data: bytes
    fields: Dict[Any, Any]


class RedisRepository:
    """Expose explicit crawler storage operations with injected resilience."""

    def __init__(
        self,
        slot: ResourceSlot[RedisClient],
        retry_policy: RetryPolicy,
    ) -> None:
        """Bind Redis semantics to a replaceable client slot."""
        self._slot = slot
        self._retry_policy = retry_policy
        self._stream_groups_initialized = set()

    @property
    def client(self) -> RedisClient:
        """Expose the native client for deliberate advanced extensions."""
        return self._slot.get()

    @property
    def redis_mode(self) -> str:
        """Return the configured Redis topology."""
        return self.client.redis_mode

    @property
    def cluster_nodes(self) -> List[str]:
        """Return normalized cluster node identifiers."""
        return list(self.client.cluster_nodes)

    async def _run(self, operation: Any, allow_during_shutdown: bool = False) -> Any:
        """Execute one repository operation through the service retry policy."""
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

    async def rpush(self, key: str, value: bytes) -> Any:
        """Append one request payload."""
        return await self._run(lambda: self.client.rpush(key, value))

    async def llen(self, key: str) -> int:
        """Return a list length."""
        return int(await self._run(lambda: self.client.llen(key)))

    async def delete(self, key: str) -> int:
        """Delete one key, including during graceful shutdown."""
        return int(
            await self._run(
                lambda: self.client.delete(key),
                allow_during_shutdown=True,
            )
        )

    async def expire(self, key: str, seconds: int) -> Any:
        """Set an expiry on one key."""
        return await self._run(lambda: self.client.expire(key, seconds))

    async def sadd(self, key: str, value: Union[str, bytes]) -> Any:
        """Add one set member."""
        return await self._run(lambda: self.client.sadd(key, value))

    def pipeline(self) -> Any:
        """Return a native pipeline for one explicitly controlled batch."""
        return self.client.pipeline()

    async def hset(self, key: str, field: str, value: bytes) -> Any:
        """Set one hash field."""
        return await self._run(lambda: self.client.hset(key, field, value))

    async def hget(self, key: str, field: str) -> Optional[bytes]:
        """Read one hash field."""
        return await self._run(lambda: self.client.hget(key, field))

    async def xadd(self, key: str, fields: Dict[Any, Any]) -> Any:
        """Append one stream message."""
        return await self._run(lambda: self.client.xadd(key, fields))

    async def dequeue_request(
        self,
        queue_key: str,
        timeout: float = 2,
        decode_responses: bool = False,
    ) -> Optional[Any]:
        """Pop one list request with cluster-safe bounded polling."""

        async def operation() -> Optional[Any]:
            """Poll the configured Redis list once."""
            if self.redis_mode == "cluster":
                request = await self.client.lpop(queue_key)
                if request is None:
                    await asyncio.sleep(min(float(timeout), 0.2))
                    return None
            else:
                result = await self.client.blpop(queue_key, timeout=timeout)
                if not result:
                    return None
                _, request = result
            if decode_responses and isinstance(request, bytes):
                return request.decode("utf-8")
            return request

        return await self._run(operation)

    async def do_filter(self, fingerprint: str, key_new_seen: str, key_is_req: str) -> int:
        """Atomically perform SET-based distributed deduplication."""
        script = """
        local fingerprint = ARGV[1]
        if redis.call('SADD', KEYS[1], fingerprint) == 1 then
            if redis.call('SADD', KEYS[2], fingerprint) == 1 then
                redis.call('SREM', KEYS[2], fingerprint)
                return 1
            end
        end
        return 0
        """
        return int(
            await self._run(
                lambda: self.client.eval(
                    script,
                    2,
                    key_new_seen,
                    key_is_req,
                    fingerprint,
                )
            )
        )

    async def do_bloom_filter(
        self,
        key_new_seen: str,
        key_is_req: str,
        index_list: List[int],
    ) -> int:
        """Atomically perform bitmap-based distributed deduplication."""
        script = """
        local indices = cjson.decode(ARGV[1])
        local is_new = 1
        for i=1,#indices do
            if redis.call('GETBIT', KEYS[1], indices[i]) == 0 then
                is_new = 1
                break
            else
                is_new = 0
            end
        end
        if is_new == 1 then
            for i=1,#indices do
                if redis.call('GETBIT', KEYS[2], indices[i]) == 0 then
                    is_new = 1
                    break
                else
                    is_new = 0
                end
            end
        end
        if is_new == 1 then
            for i=1,#indices do
                redis.call('SETBIT', KEYS[1], indices[i], 1)
            end
        end
        return is_new
        """
        return int(
            await self._run(
                lambda: self.client.eval(
                    script,
                    2,
                    key_new_seen,
                    key_is_req,
                    json.dumps(index_list),
                )
            )
        )

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
    ) -> Optional[RedisStreamMessage]:
        """Read one Redis Stream entry for a consumer group."""
        group_key = (stream_key, group_name)
        if group_key not in self._stream_groups_initialized:
            from redis.exceptions import ResponseError

            try:
                await self._run(
                    lambda: self.client.xgroup_create(
                        name=stream_key,
                        groupname=group_name,
                        id=group_start_id,
                        mkstream=mkstream,
                    )
                )
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise
            self._stream_groups_initialized.add(group_key)

        result = await self._run(
            lambda: self.client.xreadgroup(
                groupname=group_name,
                consumername=consumer_name,
                streams={stream_key: read_id},
                count=count,
                block=block,
            )
        )
        if not result or not result[0][1]:
            return None
        raw_stream_key, messages = result[0]
        message_id, fields = messages[0]
        data = self._extract_stream_data(fields, field)
        if data is None:
            return None
        return RedisStreamMessage(
            stream_key=self._to_text(raw_stream_key),
            message_id=message_id,
            data=data,
            fields=fields,
        )

    async def ack_stream_request(self, message: RedisStreamMessage, group_name: str) -> int:
        """Acknowledge one Redis Stream delivery."""
        return int(
            await self._run(
                lambda: self.client.xack(
                    message.stream_key,
                    group_name,
                    message.message_id,
                )
            )
        )

    @classmethod
    def _extract_stream_data(
        cls,
        fields: Dict[Any, Any],
        field: Optional[str],
    ) -> Optional[bytes]:
        """Normalize a configured stream field to bytes."""
        if not fields:
            return None
        value = fields.get(field) if field else None
        if value is None and field:
            value = fields.get(field.encode("utf-8"))
        if value is None and len(fields) == 1:
            value = next(iter(fields.values()))
        if value is None:
            value = json.dumps(
                {cls._to_text(key): cls._to_text(item) for key, item in fields.items()},
                ensure_ascii=False,
            ).encode("utf-8")
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        return json.dumps(value, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _to_text(value: Any) -> Any:
        """Decode Redis byte strings for metadata fields."""
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value


__all__ = ["RedisRepository", "RedisStreamMessage"]
