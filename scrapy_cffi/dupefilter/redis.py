import json
from .base import MemoryDupeFilter
from ..databases import RedisManager
from ..core.downloader.internet import Request
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..spiders import Spider
    from ..settings import SettingsInfo
    from ..cpy.cpy_resources.bloom.fallback import BloomFilterPy

class RedisDupeFilter(MemoryDupeFilter):
    def __init__(self, settings: "SettingsInfo"=None, redisManager: RedisManager=None, **kwargs):
        super().__init__(settings=settings, **kwargs)
        self.new_seen = self.settings._NEW_SEEN # Requests marked as seen but not yet sent
        self.sent_seen = self.settings._SENT_SEEN # Requests that have been seen and already sent

        self.redisManager = redisManager
        if self.redisManager.redis_mode == "cluster":
            self.cluster_nodes = [f"{n['host']}:{n['port']}" for n in self.redisManager._redis_url]
        else:
            self.cluster_nodes = ["None"]

    async def request_seen(self, request: "Request", spider: "Spider") -> bool:
        # Requests with dont_filter=True or WebSocket requests signaling connection end should not be deduplicated
        if request.dont_filter:
            return False

        fingerprint = self.get_fingerprint(request=request)
        if self.redisManager.redis_mode == "cluster": # unsupported not SCHEDULER_PERSIST
            from ..utils import get_node
            node = get_node(self.cluster_nodes, fingerprint)
            key_new_seen = f"{self.new_seen}:{node}"
            key_is_req = f"{self.sent_seen}:{node}"
        else:
            key_new_seen = self.new_seen
            key_is_req = self.sent_seen

        is_new = await self.redisManager.do_filter(
            fingerprint=fingerprint,
            key_new_seen=key_new_seen,
            key_is_req=key_is_req,
        )
        return is_new == 0

    async def mark_sent(self, request: "Request", spider: "Spider", **kwargs):
        if not request.dont_filter:
            return await self.redisManager.sadd(self.sent_seen, self.get_fingerprint(request=request))
        
class RedisBloomDupeFilter(RedisDupeFilter):
    def __init__(self, settings: "SettingsInfo"=None, redisManager: RedisManager=None, **kwargs):
        super().__init__(settings=settings, redisManager=redisManager, **kwargs)
        import bloom
        self.bloomFilter: "BloomFilterPy" = bloom.BloomFilter(size=self.settings.BLOOM_INFO.SIZE, expected=self.settings.BLOOM_INFO.EXPECTED, hash_count=self.settings.BLOOM_INFO.HASH_COUNT)

    async def request_seen(self, request: "Request", spider: "Spider") -> bool:
        # Requests with dont_filter=True or WebSocket requests signaling connection end should not be deduplicated
        if request.dont_filter:
            return False

        origin_fp_bytes = self.create_bytes(request=request)
        index_list = self.bloomFilter.get_indices(origin_fp_bytes)
        if self.redisManager.redis_mode == "cluster": # unsupported not SCHEDULER_PERSIST
            from ..utils import get_node
            node = get_node(self.cluster_nodes, json.dumps(index_list, separators=(",", ":")))
            key_new_seen = f"{self.new_seen}:{node}"
            key_is_req = f"{self.sent_seen}:{node}"
        else:
            key_new_seen = self.new_seen
            key_is_req = self.sent_seen

        is_new = await self.redisManager.do_bloom_filter(
            key_new_seen=key_new_seen,
            key_is_req=key_is_req,
            index_list=index_list
        )
        return is_new == 0

    async def mark_sent(self, request: "Request", spider: "Spider", **kwargs):
        if not request.dont_filter:
            pipe = self.redisManager.pipeline()
            origin_fp_bytes = self.create_bytes(request=request)
            if self.redisManager.redis_mode == "cluster": # unsupported not SCHEDULER_PERSIST
                from ..utils import get_node
                node = get_node(self.cluster_nodes, origin_fp_bytes)
                key_is_req = f"{self.sent_seen}:{node}"
            else:
                key_is_req = self.sent_seen

            for idx in self.bloomFilter.get_indices(origin_fp_bytes):
                pipe.setbit(key_is_req, idx, 1)
            return await pipe.execute()