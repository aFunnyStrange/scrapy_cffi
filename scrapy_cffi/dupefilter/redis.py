import json
from .base import MemoryDupeFilter
from .routing import DedupKeyRouter
from ..databases import RedisManager
from ..core.downloader.internet import Request
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..spiders import Spider
    from ..settings import SettingsInfo
    from ..cpy.cpy_resources.bloom.fallback import BloomFilterPy

class RedisDupeFilter(MemoryDupeFilter):
    def __init__(self, settings: "SettingsInfo"=None, redisManager: RedisManager=None, redis_namespace: str = "", **kwargs):
        super().__init__(settings=settings, **kwargs)
        self.redisManager = redisManager
        if not self.redisManager:
            raise ValueError("RedisDupeFilter requires redisManager")
        self._key_router = DedupKeyRouter.from_redis_manager(
            settings=self.settings,
            redis_manager=self.redisManager,
            namespace=redis_namespace,
        )

    async def request_seen(self, request: "Request", spider: "Spider") -> bool:
        if request.dont_filter:
            return False

        fingerprint = self.get_fingerprint(request=request)
        keys = self._key_router.for_fingerprint(fingerprint)

        is_new = await self.redisManager.do_filter(
            fingerprint=fingerprint,
            key_new_seen=keys.new_seen,
            key_is_req=keys.sent_seen,
        )
        if self.settings.DEDUP_TTL > 0:
            await self.redisManager.expire(keys.new_seen, self.settings.DEDUP_TTL)
            await self.redisManager.expire(keys.sent_seen, self.settings.DEDUP_TTL)
        return is_new == 0

    async def mark_sent(self, request: "Request", spider: "Spider", **kwargs):
        if not request.dont_filter:
            fingerprint = self.get_fingerprint(request=request)
            keys = self._key_router.for_fingerprint(fingerprint)
            return await self.redisManager.sadd(keys.sent_seen, fingerprint)


class RedisBloomDupeFilter(RedisDupeFilter):
    def __init__(self, settings: "SettingsInfo"=None, redisManager: RedisManager=None, redis_namespace: str = "", **kwargs):
        super().__init__(settings=settings, redisManager=redisManager, redis_namespace=redis_namespace, **kwargs)
        import bloom
        self.bloomFilter: "BloomFilterPy" = bloom.BloomFilter(
            size=self.settings.BLOOM_INFO.SIZE,
            expected=self.settings.BLOOM_INFO.EXPECTED,
            hash_count=self.settings.BLOOM_INFO.HASH_COUNT,
        )

    async def request_seen(self, request: "Request", spider: "Spider") -> bool:
        if request.dont_filter:
            return False

        origin_fp_bytes = self.create_bytes(request=request)
        index_list = self.bloomFilter.get_indices(origin_fp_bytes)
        keys = self._key_router.for_fingerprint(
            json.dumps(index_list, separators=(",", ":"))
        )

        is_new = await self.redisManager.do_bloom_filter(
            key_new_seen=keys.new_seen,
            key_is_req=keys.sent_seen,
            index_list=index_list,
        )
        if self.settings.DEDUP_TTL > 0:
            await self.redisManager.expire(keys.new_seen, self.settings.DEDUP_TTL)
            await self.redisManager.expire(keys.sent_seen, self.settings.DEDUP_TTL)
        return is_new == 0

    async def mark_sent(self, request: "Request", spider: "Spider", **kwargs):
        if not request.dont_filter:
            origin_fp_bytes = self.create_bytes(request=request)
            keys = self._key_router.for_fingerprint(origin_fp_bytes)
            pipe = self.redisManager.pipeline()
            for idx in self.bloomFilter.get_indices(origin_fp_bytes):
                pipe.setbit(keys.sent_seen, idx, 1)
            return await pipe.execute()
