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
import json
import redis.asyncio as redis
from redis.exceptions import ConnectionError, TimeoutError
from tenacity import retry, wait_fixed, retry_if_exception_type
from functools import wraps
import inspect, asyncio
from typing import TYPE_CHECKING, Union, Tuple, List, Dict
if TYPE_CHECKING:
    from ..crawler import Crawler
    from redis.asyncio.client import Redis
    from redis.asyncio.connection import ConnectionPool

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
    def __init__(
        self,
        stop_event: asyncio.Event,
        redis_url: Union[str, List[Tuple[str, int]], List[Dict]],
        redis_mode: str = "single",
        master_name: str = None,
        **kwargs
    ):
        self.stop_event = stop_event
        self.redis_mode = redis_mode
        self._redis_url = redis_url
        self._master_name = master_name
        self._method_cache = {}
        self._sentinel = None

        if redis_mode == "single":
            tmp_instance: "Redis" = redis.from_url(redis_url, **kwargs)
        elif redis_mode == "sentinel":
            if not isinstance(redis_url, list):
                raise ValueError("Sentinel mode requires a list of (host, port)")
            from redis.sentinel import Sentinel
            self._sentinel = Sentinel(redis_url, **kwargs)
            tmp_instance = self._sentinel.master_for(master_name, **kwargs)
        elif redis_mode == "cluster":
            if not isinstance(redis_url, list):
                raise ValueError("Cluster mode requires a list of dict [{'host':..., 'port':...}]")
            from redis.cluster import RedisCluster
            tmp_instance = RedisCluster(startup_nodes=redis_url, **kwargs)
        else:
            raise ValueError(f"Unsupported redis_mode: {redis_mode}")

        super().__init__(
            connection_pool=tmp_instance.connection_pool,
            **{k: v for k, v in kwargs.items() if k in redis.Redis.__init__.__code__.co_varnames}
        )

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            redis_mode=crawler.settings.REDIS_INFO.MODE,
            redis_url=crawler.settings.REDIS_INFO.resolved_url,
            master_name=crawler.settings.REDIS_INFO.MASTER_NAME
        )

    async def _reconnect(self):
        if self.stop_event.is_set():
            return
        await self.close()
        if self.redis_mode == "single":
            new_instance: "Redis" = redis.from_url(self._redis_url)
            self.connection_pool: "ConnectionPool" = new_instance.connection_pool

        elif self.redis_mode == "sentinel":
            master = self._sentinel.master_for(self._master_name)
            self.connection_pool: "ConnectionPool"  = master.connection_pool

        elif self.redis_mode == "cluster":
            from redis.cluster import RedisCluster
            new_instance: RedisCluster  = RedisCluster(startup_nodes=self._redis_url)
            self.connection_pool: "ConnectionPool"  = new_instance.connection_pool

    def __getattribute__(self, name: str):
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
                    if (name not in allowed_during_shutdown) or \
                        (name == "execute_command" and args[0] != "DEL") or \
                        (name == "parse_response" and args[1] != "DEL"):
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
    async def do_filter(self, fingerprint: str, key_new_seen: str, key_is_req: str):
        script = """
        local fingerprint = ARGV[1]
        if redis.call("SADD", KEYS[1], fingerprint) == 1 then
            if redis.call("SADD", KEYS[2], fingerprint) == 1 then
                redis.call("SREM", KEYS[2], fingerprint)
                return 1
            end
        end
        return 0
        """
        return await self.eval(
            script,
            2,
            key_new_seen,
            key_is_req,
            fingerprint
        )
    
    @auto_retry
    async def do_bloom_filter(
        self,
        key_new_seen: str,
        key_is_req: str,
        index_list: list[int]
    ) -> int:
        script = """
        local key_new_seen = KEYS[1]
        local key_is_req = KEYS[2]
        local indices = cjson.decode(ARGV[1])
        local is_new = 1

        for i=1,#indices do
            if redis.call("GETBIT", key_new_seen, indices[i]) == 0 then
                is_new = 1
                break
            else
                is_new = 0
            end
        end

        if is_new == 1 then
            for i=1,#indices do
                if redis.call("GETBIT", key_is_req, indices[i]) == 0 then
                    is_new = 1
                    break
                else
                    is_new = 0
                end
            end
        end

        if is_new == 1 then
            for i=1,#indices do
                redis.call("SETBIT", key_new_seen, indices[i], 1)
            end
        end

        return is_new
        """
        indices_json = json.dumps(index_list)
        return await self.eval(script, 2, key_new_seen, key_is_req, indices_json)

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