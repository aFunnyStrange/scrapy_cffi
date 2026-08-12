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
    from ..repo.contracts import RedisRepositoryProtocol
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
        algorithm: str = "",
    ):
        suffix_parts = [value for value in (namespace, algorithm) if value]
        suffix = ":" + ":".join(suffix_parts) if suffix_parts else ""
        self._base_new = f"{base_new_seen}{suffix}"
        self._base_sent = f"{base_sent_seen}{suffix}"
        mode_value = getattr(redis_mode, "value", redis_mode)
        self._redis_mode = str(mode_value)
        self._cluster_nodes = list(cluster_nodes or [])

    @classmethod
    def from_redis_repository(
        cls,
        settings: "SettingsInfo",
        redis_repository: "RedisRepositoryProtocol",
        namespace: str = "",
        algorithm: str = "",
    ) -> "DedupKeyRouter":
        cluster_nodes: Optional[List[str]] = None
        if redis_repository.redis_mode == "cluster":
            cluster_nodes = list(redis_repository.cluster_nodes)
        return cls(
            base_new_seen=settings._NEW_SEEN,
            base_sent_seen=settings._SENT_SEEN,
            redis_mode=redis_repository.redis_mode,
            cluster_nodes=cluster_nodes,
            namespace=namespace,
            algorithm=algorithm,
        )

    @property
    def is_cluster(self) -> bool:
        return self._redis_mode == "cluster" and bool(self._cluster_nodes)

    def for_fingerprint(self, fingerprint: Union[str, bytes]) -> DedupKeys:
        if self.is_cluster:
            from ..utils.algorithm import get_node

            node = get_node(self._cluster_nodes, fingerprint)
            # Both Lua KEYS must share one Redis Cluster slot. Redis hashes only
            # the text inside {...}, so keep the independently named SET/bitmap
            # keys under a common per-shard hash tag.
            hash_tag = self._cluster_hash_tag(node)
            return DedupKeys(
                new_seen=f"{self._base_new}:{{{hash_tag}}}",
                sent_seen=f"{self._base_sent}:{{{hash_tag}}}",
            )
        return DedupKeys(new_seen=self._base_new, sent_seen=self._base_sent)

    def _cluster_hash_tag(self, node: str) -> str:
        return "scrapy-cffi-dedup:%s:%s" % (self._base_new, node)

    def cleanup_keys(self) -> List[str]:
        """Redis keys to delete on shutdown when SCHEDULER_PERSIST is False."""
        if self.is_cluster:
            out: List[str] = []
            for node in self._cluster_nodes:
                hash_tag = self._cluster_hash_tag(node)
                out.append(f"{self._base_new}:{{{hash_tag}}}")
                out.append(f"{self._base_sent}:{{{hash_tag}}}")
            return out
        return [self._base_new, self._base_sent]


__all__ = [
    "DedupKeys",
    "DedupKeyRouter",
]
