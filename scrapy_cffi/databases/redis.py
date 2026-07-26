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
from redis.exceptions import ConnectionError, ResponseError, TimeoutError
from dataclasses import dataclass
import inspect, asyncio
from typing import TYPE_CHECKING, Union, Tuple, List, Dict, Optional
from ..utils.reconnect import AsyncReconnectController
if TYPE_CHECKING:
    from ..crawler import Crawler
    from ..models.databases import RedisInfo
    from redis.asyncio.client import Redis
    from redis.asyncio.connection import ConnectionPool

@dataclass
class RedisStreamMessage:
    stream_key: str
    message_id: Union[str, bytes]
    data: bytes
    fields: Dict


class RedisManager(redis.Redis):
    def __init__(
        self,
        stop_event: asyncio.Event,
        redis_url: Union[str, List[Tuple[str, int]], List[Dict]],
        redis_mode: str = "single",
        master_name: str = None,
        sentinel_override_master: Tuple[str,int]=None,
        sentinel_username: str = None,
        sentinel_password: str = None,
        cluster_address_remap: Dict[str, str] = None,
        **kwargs
    ):
        self.stop_event = stop_event
        self.redis_mode = redis_mode
        self._redis_url = redis_url
        self._master_name = master_name
        self._sentinel_override_master = sentinel_override_master
        self._cluster_address_remap_table = cluster_address_remap or {}
        self._connection_kwargs = dict(kwargs)
        self._sentinel = None
        self._cluster_client = None
        self._stream_groups_initialized = set()

        if redis_mode == "single":
            tmp_instance: "Redis" = redis.from_url(redis_url, **kwargs)
        elif redis_mode == "sentinel":
            if not isinstance(redis_url, list):
                raise ValueError("Sentinel mode requires a list of (host, port)")
            from redis.asyncio.sentinel import Sentinel
            sentinel_kwargs = {
                key: value
                for key, value in kwargs.items()
                if key.startswith("socket_") or key in {"ssl", "ssl_cert_reqs"}
            }
            sentinel_kwargs.update({
                key: value
                for key, value in {
                    "username": sentinel_username,
                    "password": sentinel_password,
                }.items()
                if value is not None
            })
            self._sentinel = Sentinel(
                redis_url,
                sentinel_kwargs=sentinel_kwargs or None,
                **kwargs,
            )
            if self._sentinel_override_master:
                host, port = self._sentinel_override_master
                tmp_instance = redis.Redis(host=host, port=port, **kwargs)
            else:
                tmp_instance = self._sentinel.master_for(master_name, **kwargs)
        elif redis_mode == "cluster":
            if not isinstance(redis_url, list):
                raise ValueError("Cluster mode requires a list of dict [{'host':..., 'port':...}] or list of URLs")
            from redis.asyncio.cluster import RedisCluster
            startup_nodes = self._build_cluster_startup_nodes(redis_url)
            tmp_instance = RedisCluster(
                startup_nodes=startup_nodes,
                decode_responses=False,
                require_full_coverage=False,
                address_remap=self._cluster_address_remap,
                **kwargs,
            )
            self._cluster_client = tmp_instance
        else:
            raise ValueError(f"Unsupported redis_mode: {redis_mode}")
        if self.redis_mode == "cluster":
            # Keep a lightweight base Redis instance for compatibility, while real I/O
            # is delegated to `_cluster_client` via __getattribute__.
            super().__init__(host="127.0.0.1", port=6379, decode_responses=False)
        else:
            super().__init__(
                connection_pool=tmp_instance.connection_pool,
                **{k: v for k, v in kwargs.items() if k in redis.Redis.__init__.__code__.co_varnames}
            )
        self._reconnect_controller = AsyncReconnectController(
            self.stop_event,
            self._reconnect,
            (ConnectionError, TimeoutError),
            label="Redis",
        )

    @classmethod
    def from_redis_info(cls, stop_event: asyncio.Event, info: "RedisInfo"):
        from ..models.databases import RedisMode

        if not info.resolved_url:
            raise ValueError("RedisManager.from_redis_info requires a configured REDIS_INFO URL or nodes")
        mode = info.MODE if isinstance(info.MODE, str) else info.MODE.value
        connection_kwargs = {
            "username": info.USERNAME,
            "password": info.PASSWORD,
            "socket_connect_timeout": info.CONNECT_TIMEOUT,
            "socket_timeout": info.SOCKET_TIMEOUT,
            "protocol": info.PROTOCOL,
        }
        if info.SSL and info.SSL_CERT_REQS is not None:
            connection_kwargs["ssl_cert_reqs"] = info.SSL_CERT_REQS
        # redis.from_url selects SSLConnection from the rediss:// scheme.
        # Sentinel/Cluster constructors instead need the explicit ssl flag.
        if info.SSL and mode != RedisMode.SINGLE.value:
            connection_kwargs["ssl"] = True
        connection_kwargs = {
            key: value for key, value in connection_kwargs.items() if value is not None
        }
        return cls(
            stop_event=stop_event,
            redis_mode=mode,
            redis_url=info.resolved_url,
            master_name=info.MASTER_NAME,
            sentinel_override_master=info.SENTINEL_OVERRIDE_MASTER,
            sentinel_username=info.SENTINEL_USERNAME,
            sentinel_password=info.SENTINEL_PASSWORD,
            cluster_address_remap=info.CLUSTER_ADDRESS_REMAP,
            **connection_kwargs,
        )

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls.from_redis_info(crawler.stop_event, crawler.settings.REDIS_INFO)

    async def _reconnect(self):
        await self._close_active_client(close_sentinel=False)
        
        if self.redis_mode == "single":
            new_instance: "Redis" = redis.from_url(self._redis_url, **self._connection_kwargs)
            self.connection_pool: "ConnectionPool" = new_instance.connection_pool
        elif self.redis_mode == "sentinel":
            if self._sentinel_override_master:
                host, port = self._sentinel_override_master
                new_instance = redis.Redis(
                    host=host,
                    port=port,
                    **self._connection_kwargs,
                )
                self.connection_pool: "ConnectionPool" = new_instance.connection_pool
            else:
                master = self._sentinel.master_for(
                    self._master_name,
                    **self._connection_kwargs,
                )
                self.connection_pool: "ConnectionPool" = master.connection_pool
        elif self.redis_mode == "cluster":
            from redis.asyncio.cluster import RedisCluster
            new_instance: RedisCluster = RedisCluster(
                startup_nodes=self._build_cluster_startup_nodes(self._redis_url),
                decode_responses=False,
                require_full_coverage=False,
                address_remap=self._cluster_address_remap,
                **self._connection_kwargs,
            )
            self._cluster_client = new_instance

    def _build_cluster_startup_nodes(self, redis_url):
        from redis.asyncio.cluster import ClusterNode
        if not redis_url:
            raise ValueError("Redis cluster startup_nodes cannot be empty")
        if isinstance(redis_url[0], str):
            from urllib.parse import urlparse
            nodes = []
            for value in redis_url:
                parsed = urlparse(value if "://" in value else f"//{value}")
                if not parsed.hostname or not parsed.port:
                    raise ValueError(f"Invalid Redis cluster node: {value!r}")
                nodes.append(ClusterNode(host=parsed.hostname, port=parsed.port))
            return nodes
        if isinstance(redis_url[0], dict):
            return [
                ClusterNode(host=node["host"], port=int(node["port"]))
                for node in redis_url
            ]
        return redis_url

    def _cluster_address_remap(self, address):
        host, port = address
        if host in self._cluster_address_remap_table:
            return (self._cluster_address_remap_table[host], port)
        if host in {"host.docker.internal", "localhost"}:
            return ("127.0.0.1", port)
        return (host, port)

    async def execute_command(self, *args, **options):
        """Protect Redis' single command gateway while retaining the Redis API type."""
        command = args[0] if args else ""
        if isinstance(command, bytes):
            command = command.decode("ascii", errors="ignore")
        allow_during_shutdown = str(command).upper() == "DEL"

        async def operation():
            if self._cluster_client is not None:
                return await self._cluster_client.execute_command(*args, **options)
            return await super(RedisManager, self).execute_command(*args, **options)

        coroutine = self._reconnect_controller.run(
            operation,
            allow_during_shutdown=allow_during_shutdown,
        )
        if allow_during_shutdown and self.stop_event.is_set():
            return await asyncio.wait_for(coroutine, timeout=3)
        return await coroutine

    async def close(self):
        """Close the active async client even after the crawler stop flag is set."""
        await self._close_active_client(close_sentinel=True)

    async def _close_active_client(self, close_sentinel: bool):
        cluster_client = self._cluster_client
        self._cluster_client = None
        if cluster_client is not None:
            cluster_close = getattr(cluster_client, "aclose", cluster_client.close)
            result = cluster_close()
            if inspect.isawaitable(result):
                await result

        if close_sentinel and self._sentinel is not None:
            sentinel_closes = []
            for sentinel_client in self._sentinel.sentinels:
                sentinel_close = getattr(sentinel_client, "aclose", sentinel_client.close)
                result = sentinel_close()
                if inspect.isawaitable(result):
                    sentinel_closes.append(result)
            if sentinel_closes:
                await asyncio.gather(*sentinel_closes, return_exceptions=True)

        base_close = getattr(super(), "aclose", super().close)
        result = base_close()
        if inspect.isawaitable(result):
            await result

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

    async def dequeue_request(self, queue_key, timeout=2, decode_responses=False): # Pop a request from the queue, with optional timeout and decoding.
        if self.redis_mode == "cluster":
            # Multiple BLPOP consumers aimed at one cluster node can occupy the
            # node pool and starve a different start queue indefinitely. Short
            # non-blocking polling keeps start/work queues fair across slots.
            request = await self.lpop(queue_key)
            if request is None:
                await asyncio.sleep(min(float(timeout), 0.2))
                return None
        else:
            result = await self.blpop(queue_key, timeout=timeout)
            if not result:
                return None
            _, request = result
        if decode_responses and isinstance(request, bytes):
            request = request.decode('utf-8')
        return request

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
        group_key = (stream_key, group_name)
        if group_key not in self._stream_groups_initialized:
            try:
                await self.xgroup_create(
                    name=stream_key,
                    groupname=group_name,
                    id=group_start_id,
                    mkstream=mkstream,
                )
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise
            self._stream_groups_initialized.add(group_key)

        result = await self.xreadgroup(
            groupname=group_name,
            consumername=consumer_name,
            streams={stream_key: read_id},
            count=count,
            block=block,
        )
        if not result:
            return None

        raw_stream_key, messages = result[0]
        if not messages:
            return None

        message_id, fields = messages[0]
        data = self._extract_stream_data(fields=fields, field=field)
        if data is None:
            return None

        return RedisStreamMessage(
            stream_key=self._to_text(raw_stream_key),
            message_id=message_id,
            data=data,
            fields=fields,
        )

    async def ack_stream_request(self, message: RedisStreamMessage, group_name: str):
        return await self.xack(message.stream_key, group_name, message.message_id)

    def _extract_stream_data(self, fields: Dict, field: Optional[str]) -> Optional[bytes]:
        if not fields:
            return None

        value = None
        if field:
            value = fields.get(field)
            if value is None:
                value = fields.get(field.encode("utf-8"))
            if value is None and len(fields) == 1:
                value = next(iter(fields.values()))
        elif len(fields) == 1:
            value = next(iter(fields.values()))
        if value is None and (not field or len(fields) > 1):
            value = json.dumps({
                self._to_text(k): self._to_text(v)
                for k, v in fields.items()
            }, ensure_ascii=False).encode("utf-8")

        if value is None:
            return None
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        return json.dumps(value, ensure_ascii=False).encode("utf-8")

    def _to_text(self, value):
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value
