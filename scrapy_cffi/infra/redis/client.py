"""Implement one-shot Redis connectivity for single, Sentinel, and Cluster modes."""

import inspect
from typing import Any, Dict, List, Optional, Tuple, Union, cast
from urllib.parse import urlparse

import redis.asyncio as redis

from ...config.database import RedisInfo, RedisMode


RedisEndpoint = Union[str, List[Tuple[str, int]], List[Union[Dict[str, Any], str]]]


class RedisClient(redis.Redis):
    """Expose the native async Redis API without retry or crawler policy."""

    def __init__(
        self,
        redis_url: RedisEndpoint,
        redis_mode: str = "single",
        master_name: Optional[str] = None,
        sentinel_override_master: Optional[Tuple[str, int]] = None,
        sentinel_username: Optional[str] = None,
        sentinel_password: Optional[str] = None,
        cluster_address_remap: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> None:
        """Build one Redis transport for the selected topology."""
        self.redis_mode = redis_mode
        self.redis_url = redis_url
        self.cluster_nodes = self._normalize_cluster_nodes(redis_url, redis_mode)
        self._cluster_address_remap_table = cluster_address_remap or {}
        self._sentinel = None
        self._cluster_client = None

        if redis_mode == RedisMode.SINGLE.value:
            instance = redis.from_url(cast(str, redis_url), **kwargs)
        elif redis_mode == RedisMode.SENTINEL.value:
            if not isinstance(redis_url, list):
                raise ValueError("Sentinel mode requires a list of (host, port)")
            from redis.asyncio.sentinel import Sentinel

            sentinel_kwargs = {
                key: value
                for key, value in kwargs.items()
                if key.startswith("socket_") or key in {"ssl", "ssl_cert_reqs"}
            }
            sentinel_kwargs.update(
                {
                    key: value
                    for key, value in {
                        "username": sentinel_username,
                        "password": sentinel_password,
                    }.items()
                    if value is not None
                }
            )
            self._sentinel = Sentinel(
                redis_url,
                sentinel_kwargs=sentinel_kwargs or None,
                **kwargs,
            )
            if sentinel_override_master:
                host, port = sentinel_override_master
                instance = redis.Redis(host=host, port=port, **kwargs)
            else:
                if not master_name:
                    raise ValueError("Sentinel mode requires MASTER_NAME")
                instance = self._sentinel.master_for(master_name, **kwargs)
        elif redis_mode == RedisMode.CLUSTER.value:
            if not isinstance(redis_url, list):
                raise ValueError("Cluster mode requires configured startup nodes")
            from redis.asyncio.cluster import RedisCluster

            instance = RedisCluster(
                startup_nodes=self._build_cluster_startup_nodes(redis_url),
                decode_responses=False,
                require_full_coverage=False,
                address_remap=self._cluster_address_remap,
                **kwargs,
            )
            self._cluster_client = instance
        else:
            raise ValueError("Unsupported redis_mode: %s" % redis_mode)

        if redis_mode == RedisMode.CLUSTER.value:
            super().__init__(host="127.0.0.1", port=6379, decode_responses=False)
        else:
            super().__init__(connection_pool=cast(Any, instance).connection_pool)

    @classmethod
    def from_info(cls, info: RedisInfo) -> "RedisClient":
        """Create a transport from validated Redis settings."""
        resolved_url = info.resolved_url
        if not resolved_url:
            raise ValueError("RedisClient requires a configured Redis URL or nodes")
        mode = info.MODE if isinstance(info.MODE, str) else info.MODE.value
        kwargs: Dict[str, Any] = {
            "username": info.USERNAME,
            "password": info.PASSWORD,
            "socket_connect_timeout": info.CONNECT_TIMEOUT,
            "socket_timeout": info.SOCKET_TIMEOUT,
            "protocol": info.PROTOCOL,
        }
        if info.SSL and info.SSL_CERT_REQS is not None:
            kwargs["ssl_cert_reqs"] = info.SSL_CERT_REQS
        if info.SSL and mode != RedisMode.SINGLE.value:
            kwargs["ssl"] = True
        return cls(
            redis_url=resolved_url,
            redis_mode=mode,
            master_name=info.MASTER_NAME,
            sentinel_override_master=info.SENTINEL_OVERRIDE_MASTER,
            sentinel_username=info.SENTINEL_USERNAME,
            sentinel_password=info.SENTINEL_PASSWORD,
            cluster_address_remap=info.CLUSTER_ADDRESS_REMAP,
            **{key: value for key, value in kwargs.items() if value is not None},
        )

    async def connect(self) -> None:
        """Validate the transport with a single ping."""
        await self.ping()

    async def execute_command(self, *args: Any, **options: Any) -> Any:
        """Execute exactly once against the active native client."""
        if self._cluster_client is not None:
            return await self._cluster_client.execute_command(*args, **options)
        return await super().execute_command(*args, **options)

    async def close(self, close_connection_pool: Optional[bool] = None) -> None:
        """Close all topology-specific connection pools."""
        cluster_client = self._cluster_client
        self._cluster_client = None
        if cluster_client is not None:
            close = getattr(cluster_client, "aclose", cluster_client.close)
            result = close()
            if inspect.isawaitable(result):
                await result

        if self._sentinel is not None:
            closes = []
            for sentinel_client in self._sentinel.sentinels:
                close = getattr(sentinel_client, "aclose", sentinel_client.close)
                result = close()
                if inspect.isawaitable(result):
                    closes.append(result)
            if closes:
                import asyncio

                await asyncio.gather(*closes, return_exceptions=True)

        close = getattr(super(), "aclose", super().close)
        result = close(close_connection_pool)
        if inspect.isawaitable(result):
            await result

    def _build_cluster_startup_nodes(self, values: List[Any]) -> List[Any]:
        """Convert configured cluster endpoints to redis-py nodes."""
        from redis.asyncio.cluster import ClusterNode

        nodes = []
        for value in values:
            if isinstance(value, str):
                parsed = urlparse(value if "://" in value else "//%s" % value)
                if not parsed.hostname or not parsed.port:
                    raise ValueError("Invalid Redis cluster node: %r" % value)
                nodes.append(ClusterNode(host=parsed.hostname, port=parsed.port))
            elif isinstance(value, dict):
                nodes.append(ClusterNode(host=value["host"], port=int(value["port"])))
            else:
                nodes.append(value)
        if not nodes:
            raise ValueError("Redis cluster startup_nodes cannot be empty")
        return nodes

    def _cluster_address_remap(self, address: Tuple[str, int]) -> Tuple[str, int]:
        """Map container-advertised hosts to reachable client hosts."""
        host, port = address
        if host in self._cluster_address_remap_table:
            return self._cluster_address_remap_table[host], port
        if host in {"host.docker.internal", "localhost"}:
            return "127.0.0.1", port
        return host, port

    @staticmethod
    def _normalize_cluster_nodes(redis_url: RedisEndpoint, mode: str) -> List[str]:
        """Expose stable node identifiers for deduplication key routing."""
        if mode != RedisMode.CLUSTER.value or not isinstance(redis_url, list):
            return []
        result = []
        for node in redis_url:
            if isinstance(node, dict):
                result.append("%s:%s" % (node["host"], node["port"]))
            else:
                result.append(str(node))
        return result


__all__ = ["RedisClient", "RedisEndpoint"]
