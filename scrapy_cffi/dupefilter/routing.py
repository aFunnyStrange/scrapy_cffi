"""
Redis deduplication key routing (single / cluster).

Cluster mode shards dedup keys with jump-consistent-hash so each fingerprint
maps to stable SET/BITMAP keys. This is key affinity for Redis Cluster slot
routing — not crawler load balancing.

Standalone: use DedupKeyRouter.from_redis_manager(...) without the crawler.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from ..databases.redis import RedisManager
    from ..settings import SettingsInfo


@dataclass(frozen=True)
class DedupKeys:
    new_seen: str
    sent_seen: str


class DedupKeyRouter:
    """
    Resolve ``new_seen`` / ``sent_seen`` Redis keys for a request fingerprint.

    In cluster mode, appends ``:{node_id}`` chosen by jump hash over cluster
    startup nodes so duplicate checks stay on one hash slot per fingerprint.
    """

    def __init__(
        self,
        *,
        base_new_seen: str,
        base_sent_seen: str,
        redis_mode: str,
        cluster_nodes: Optional[List[str]] = None,
        namespace: str = "",
    ):
        suffix = f":{namespace}" if namespace else ""
        self._base_new = f"{base_new_seen}{suffix}"
        self._base_sent = f"{base_sent_seen}{suffix}"
        self._redis_mode = str(redis_mode)
        self._cluster_nodes = list(cluster_nodes or [])

    @classmethod
    def from_redis_manager(
        cls,
        settings: "SettingsInfo",
        redis_manager: "RedisManager",
        namespace: str = "",
    ) -> "DedupKeyRouter":
        cluster_nodes: Optional[List[str]] = None
        if redis_manager.redis_mode == "cluster":
            cluster_nodes = [
                f"{n['host']}:{n['port']}" for n in redis_manager._redis_url
            ]
        return cls(
            base_new_seen=settings._NEW_SEEN,
            base_sent_seen=settings._SENT_SEEN,
            redis_mode=redis_manager.redis_mode,
            cluster_nodes=cluster_nodes,
            namespace=namespace,
        )

    @property
    def is_cluster(self) -> bool:
        return self._redis_mode == "cluster" and bool(self._cluster_nodes)

    def for_fingerprint(self, fingerprint: Union[str, bytes]) -> DedupKeys:
        if self.is_cluster:
            from ..utils.algorithm import get_node

            node = get_node(self._cluster_nodes, fingerprint)
            return DedupKeys(
                new_seen=f"{self._base_new}:{node}",
                sent_seen=f"{self._base_sent}:{node}",
            )
        return DedupKeys(new_seen=self._base_new, sent_seen=self._base_sent)

    def cleanup_keys(self) -> List[str]:
        """Redis keys to delete on shutdown when SCHEDULER_PERSIST is False."""
        if self.is_cluster:
            out: List[str] = []
            for node in self._cluster_nodes:
                out.append(f"{self._base_new}:{node}")
                out.append(f"{self._base_sent}:{node}")
            return out
        return [self._base_new, self._base_sent]


__all__ = [
    "DedupKeys",
    "DedupKeyRouter",
]
