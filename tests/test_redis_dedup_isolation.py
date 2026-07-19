"""Redis scheduler: ingress start URLs vs discovered link dedup."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_redis_put_skips_dedup_for_start_url():
    from scrapy_cffi.core.scheduler.redis import RedisScheduler
    from scrapy_cffi.core.downloader.internet import HttpRequest

    stop = asyncio.Event()
    settings = MagicMock()
    settings.DUPEFILTER = None
    settings.FILTER_KEY = "cffiFilter"
    settings._NEW_SEEN = "cffiFilter_new_seen"
    settings._SENT_SEEN = "cffiFilter_sent_seen"
    settings.DEDUP_TTL = 0
    settings.SCHEDULER_PERSIST = False

    redis_mgr = MagicMock()
    redis_mgr.rpush = AsyncMock(return_value=1)

    sch = RedisScheduler(
        spiders_name=["customRedisSpider"],
        stop_event=stop,
        settings=settings,
        sessions=MagicMock(),
        sessions_lock=asyncio.Lock(),
        signalManager=MagicMock(),
        redisManager=redis_mgr,
    )
    sch.dupefilter = MagicMock()
    sch.dupefilter.request_seen = AsyncMock(return_value=True)

    spider = MagicMock()
    spider.name = "customRedisSpider"
    req = HttpRequest(url="http://127.0.0.1:8002", method="GET")
    req.meta["is_start_url"] = True

    async def run():
        ok = await sch.put(req, spider)
        assert ok is True
        sch.dupefilter.request_seen.assert_not_called()
        assert redis_mgr.rpush.await_count == 1

    asyncio.run(run())


def test_redis_namespace_per_spider():
    from scrapy_cffi.dupefilter.routing import DedupKeyRouter

    class FakeRedis:
        redis_mode = "single"
        _redis_url = []

    class FakeSettings:
        _NEW_SEEN = "cffiFilter_new_seen"
        _SENT_SEEN = "cffiFilter_sent_seen"

    r1 = DedupKeyRouter.from_redis_manager(FakeSettings(), FakeRedis(), namespace="customRedisSpider")
    r2 = DedupKeyRouter.from_redis_manager(FakeSettings(), FakeRedis(), namespace="student")
    k1 = r1.for_fingerprint("abc")
    k2 = r2.for_fingerprint("abc")
    assert k1.new_seen != k2.new_seen
    assert ":customRedisSpider" in k1.new_seen
    assert ":student" in k2.new_seen


def test_dedup_cleanup_keys_single_and_cluster():
    from scrapy_cffi.dupefilter.routing import DedupKeyRouter

    single = DedupKeyRouter(
        base_new_seen="cffiFilter_new_seen",
        base_sent_seen="cffiFilter_sent_seen",
        redis_mode="single",
        namespace="demo",
    )
    assert single.cleanup_keys() == [
        "cffiFilter_new_seen:demo",
        "cffiFilter_sent_seen:demo",
    ]

    cluster = DedupKeyRouter(
        base_new_seen="cffiFilter_new_seen",
        base_sent_seen="cffiFilter_sent_seen",
        redis_mode="cluster",
        cluster_nodes=["127.0.0.1:7000", "127.0.0.1:7001"],
        namespace="demo",
    )
    keys = cluster.cleanup_keys()
    assert len(keys) == 4
    assert "cffiFilter_new_seen:demo:127.0.0.1:7000" in keys


if __name__ == "__main__":
    test_redis_put_skips_dedup_for_start_url()
    test_redis_namespace_per_spider()
    test_dedup_cleanup_keys_single_and_cluster()
    print("ok")
