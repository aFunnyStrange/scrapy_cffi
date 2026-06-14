"""Unit tests for Redis ingress config resolution (no live Redis)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapy_cffi.databases.redis_ingress import resolve_redis_ingress
from scrapy_cffi.models import RedisIngressMode, RedisStreamConsumerInfo
from scrapy_cffi.settings import SettingsInfo


class _Spider:
    name = "demo"
    redis_key = None
    redis_start_mode = None
    redis_group = None
    redis_consumer = None


def test_spider_overrides_settings():
    settings = SettingsInfo()
    settings.REDIS_STREAM_INFO = RedisStreamConsumerInfo(
        MODE=RedisIngressMode.STREAM,
        STREAM_KEY="from-settings",
        GROUP_NAME="g1",
    )
    spider = _Spider()
    spider.redis_key = "from-spider"
    spider.redis_start_mode = "list"
    cfg = resolve_redis_ingress(spider=spider, settings=settings)
    assert cfg.stream_key == "from-spider"
    assert cfg.mode == RedisIngressMode.LIST
    assert not cfg.is_stream


def test_settings_defaults_for_stream():
    settings = SettingsInfo()
    settings.REDIS_STREAM_INFO = RedisStreamConsumerInfo(
        MODE=RedisIngressMode.STREAM,
        STREAM_KEY="tasks:stream",
        GROUP_NAME="workers",
        BLOCK_MS=999,
    )
    spider = _Spider()
    cfg = resolve_redis_ingress(spider=spider, settings=settings)
    assert cfg.stream_key == "tasks:stream"
    assert cfg.group_name == "workers"
    assert cfg.block_ms == 999
    assert cfg.consumer_name == "demo"
    assert cfg.is_stream


def test_fallback_key_without_settings():
    settings = SettingsInfo()
    spider = _Spider()
    spider.redis_key = "my-queue"
    cfg = resolve_redis_ingress(spider=spider, settings=settings)
    assert cfg.stream_key == "my-queue"
    assert cfg.mode == RedisIngressMode.LIST
