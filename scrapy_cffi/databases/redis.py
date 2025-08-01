"""
RedisManager

An async Redis client extending `redis.asyncio.Redis` with full API support.

Features:
- Automatically retries and reconnects on connection failures.
- Respects a global asyncio stop event to gracefully abort operations during shutdown.
- Only allows certain Redis commands (e.g. DEL) to run when stopping to ensure safe cleanup.
- Provides convenience methods with built-in retry for common queue and deduplication patterns.

Designed for use within an asyncio event loop and single-threaded context.
"""
import redis.asyncio as redis
from redis.exceptions import ConnectionError, TimeoutError
from tenacity import retry, wait_fixed, retry_if_exception_type
from functools import wraps
import inspect, asyncio
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..crawler import Crawler

def auto_retry(func):
    @wraps(func)
    @retry(
        wait=wait_fixed(1),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True
    )
    async def wrapper(self, *args, **kwargs):
        if self.stop_event.is_set():
            raise asyncio.CancelledError("Stop event set, abort Redis operation")
        try:
            return await func(self, *args, **kwargs)
        except (ConnectionError, TimeoutError):
            if self.stop_event.is_set():
                raise asyncio.CancelledError("Stop event set during reconnect")
            await self._reconnect()
            return await func(self, *args, **kwargs)
    return wrapper


class RedisManager(redis.Redis):
    def __init__(self, stop_event: asyncio.Event, redis_url: str, **kwargs):
        self.stop_event = stop_event
        tmp_instance = redis.from_url(redis_url, **kwargs)
        self._redis_url = redis_url
        self._method_cache = {}
        super().__init__(
            connection_pool=tmp_instance.connection_pool,
            **{k: v for k, v in kwargs.items() if k in redis.Redis.__init__.__code__.co_varnames}
        )

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event, 
            redis_url=crawler.settings.REDIS_INFO.REDIS_URL
        )

    async def _reconnect(self):
        if self.stop_event.is_set():
            return
        await self.close()
        new_instance = redis.from_url(self._redis_url)
        self.connection_pool = new_instance.connection_pool

    def __getattribute__(self, name):
        if name.startswith("_") or name in ("_method_cache", "_reconnect"):
            return super().__getattribute__(name)

        attr = super().__getattribute__(name)

        if not callable(attr) or not inspect.iscoroutinefunction(attr):
            return attr

        method_cache = super().__getattribute__("_method_cache")

        if name not in method_cache:
            @wraps(attr)
            async def wrapper(*args, **kwargs):
                allowed_during_shutdown = {"execute_command", "initialize", "parse_response"}

                if self.stop_event.is_set():
                    if (name not in allowed_during_shutdown) or (name == "execute_command" and args[0] != "DEL") or (name == "parse_response" and args[1] != "DEL"):
                        raise asyncio.CancelledError(f"Stop event set, abort Redis operation: {name}")

                try:
                    if self.stop_event.is_set() and name in allowed_during_shutdown:
                        return await asyncio.wait_for(attr(*args, **kwargs), timeout=3)
                    else:
                        return await attr(*args, **kwargs)
                except (ConnectionError, TimeoutError):
                    if self.stop_event.is_set():
                        raise asyncio.CancelledError("Stop event set during reconnect")
                    await self._reconnect()
                    return await attr(*args, **kwargs)

            method_cache[name] = wrapper

        return method_cache[name]


    @auto_retry
    async def push_if_not_seen(self, fp: str, req_bytes: bytes, key_new_seen: str, key_is_req: str, queue_key: str):
        script = """
        local fp = ARGV[1]
        if redis.call("SADD", KEYS[1], fp) == 1 then
            if redis.call("SADD", KEYS[2], fp) == 1 then
                redis.call("SREM", KEYS[2], fp)
                redis.call("RPUSH", KEYS[3], ARGV[2])
                return 1
            end
        end
        return 0
        """
        return await self.eval(
            script,
            3,
            key_new_seen,
            key_is_req,
            queue_key,
            fp,
            req_bytes
        )

    @auto_retry
    async def dequeue_request(self, queue_key, timeout=2, decode_responses=False): # Pop a request from the queue, with optional timeout and decoding.
        result = await self.blpop(queue_key, timeout=timeout)
        if result:
            _, request = result
            if decode_responses:
                request: bytes
                request = request.decode('utf-8')
            return request
        return None