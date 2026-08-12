import json
from .base import MemoryDupeFilter
from .routing import DedupKeyRouter
from ..core.downloader.internet import Request
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..platform.bloom import BloomFilterProtocol
    from ..repo.contracts import RedisRepositoryProtocol
    from ..spiders import Spider
    from ..settings import SettingsInfo

class RedisDupeFilter(MemoryDupeFilter):
    def __init__(
        self,
        settings: "SettingsInfo" = None,
        redis_repository: "RedisRepositoryProtocol" = None,
        redis_namespace: str = "",
        redis_algorithm: str = "",
        **kwargs,
    ):
        super().__init__(settings=settings, **kwargs)
        self.redis_repository = redis_repository
        if not self.redis_repository:
            raise ValueError("RedisDupeFilter requires redis_repository")
        self._key_router = DedupKeyRouter.from_redis_repository(
            settings=self.settings,
            redis_repository=self.redis_repository,
            namespace=redis_namespace,
            algorithm=redis_algorithm,
        )

    def dedup_cleanup_keys(self) -> list[str]:
        return self._key_router.cleanup_keys()

    async def request_seen(self, request: "Request", spider: "Spider") -> bool:
        if request.dont_filter:
            return False

        fingerprint = self.get_fingerprint(request=request)
        keys = self._key_router.for_fingerprint(fingerprint)

        is_new = await self.redis_repository.do_filter(
            fingerprint=fingerprint,
            key_new_seen=keys.new_seen,
            key_is_req=keys.sent_seen,
        )
        if self.settings.DEDUP_TTL > 0:
            await self.redis_repository.expire(keys.new_seen, self.settings.DEDUP_TTL)
            await self.redis_repository.expire(keys.sent_seen, self.settings.DEDUP_TTL)
        return is_new == 0

    async def mark_sent(self, request: "Request", spider: "Spider", **kwargs):
        if not request.dont_filter:
            fingerprint = self.get_fingerprint(request=request)
            keys = self._key_router.for_fingerprint(fingerprint)
            return await self.redis_repository.sadd(keys.sent_seen, fingerprint)


class RedisBloomDupeFilter(RedisDupeFilter):
    def __init__(
        self,
        settings: "SettingsInfo" = None,
        redis_repository: "RedisRepositoryProtocol" = None,
        redis_namespace: str = "",
        **kwargs,
    ):
        from ..platform.bloom import bloom_filter_factory

        super().__init__(
            settings=settings,
            redis_repository=redis_repository,
            redis_namespace=redis_namespace,
            redis_algorithm=bloom_filter_factory.algorithm_name,
            **kwargs,
        )
        self.bloomFilter: "BloomFilterProtocol" = bloom_filter_factory.create(
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

        is_new = await self.redis_repository.do_bloom_filter(
            key_new_seen=keys.new_seen,
            key_is_req=keys.sent_seen,
            index_list=index_list,
        )
        if self.settings.DEDUP_TTL > 0:
            await self.redis_repository.expire(keys.new_seen, self.settings.DEDUP_TTL)
            await self.redis_repository.expire(keys.sent_seen, self.settings.DEDUP_TTL)
        return is_new == 0

    async def mark_sent(self, request: "Request", spider: "Spider", **kwargs):
        if not request.dont_filter:
            origin_fp_bytes = self.create_bytes(request=request)
            index_list = self.bloomFilter.get_indices(origin_fp_bytes)
            keys = self._key_router.for_fingerprint(
                json.dumps(index_list, separators=(",", ":"))
            )
            pipe = self.redis_repository.pipeline()
            for idx in index_list:
                pipe.setbit(keys.sent_seen, idx, 1)
            return await pipe.execute()
