"""Verify Bloom backend selection and distributed index compatibility."""

import asyncio
from typing import Any, Dict, List, Optional

import pytest
from pydantic import ValidationError

from scrapy_cffi.core.downloader.internet import HttpRequest
from scrapy_cffi.dupefilter.redis import RedisBloomDupeFilter
from scrapy_cffi.platform.bloom import (
    BloomFilterFactory,
    PythonBloomFilter,
)
from scrapy_cffi.settings import SettingsInfo


class _MissingNativeImporter:
    """Simulate an environment without the optional Rust wheel."""

    def __call__(self, name: str) -> Any:
        """Raise the same error produced by Python's import system."""
        raise ModuleNotFoundError(name=name)


class _FakePipeline:
    """Record Redis bitmap writes without external infrastructure."""

    def __init__(self) -> None:
        """Initialize an empty operation log."""
        self.operations: List[Any] = []

    def setbit(self, key: str, index: int, value: int) -> None:
        """Record one bitmap mutation."""
        self.operations.append((key, index, value))

    async def execute(self) -> List[Any]:
        """Return the recorded pipeline operations."""
        return self.operations


class _FakeRedisRepository:
    """Implement the repository subset required by RedisBloomDupeFilter."""

    redis_mode = "single"
    cluster_nodes: List[str] = []

    def __init__(self) -> None:
        """Store Bloom keys, indices, and pipeline evidence."""
        self.last_filter: Optional[Any] = None
        self.last_pipeline: Optional[_FakePipeline] = None

    async def do_bloom_filter(
        self,
        key_new_seen: str,
        key_is_req: str,
        index_list: List[int],
    ) -> int:
        """Capture one atomic Bloom operation and report a new value."""
        self.last_filter = (key_new_seen, key_is_req, index_list)
        return 1

    async def expire(self, key: str, ttl: int) -> None:
        """Accept optional expiry calls used by the filter."""
        del key, ttl

    def pipeline(self) -> _FakePipeline:
        """Return one recording bitmap pipeline."""
        self.last_pipeline = _FakePipeline()
        return self.last_pipeline


def test_python_backend_roundtrip_and_dimensions() -> None:
    """Exercise portable membership, clearing, and optimized indices."""
    bloom = PythonBloomFilter(size=1_001, expected=100, hash_count=7)
    assert bloom.size == 1_008
    assert not bloom.exists(b"hello")
    bloom.add(b"hello")
    assert bloom.exists(b"hello")
    assert len(bloom.get_indices(b"hello")) == 7
    assert max(bloom.get_indices(b"hello")) < bloom.size
    bloom.clear()
    assert not bloom.exists(b"hello")


def test_factory_falls_back_without_a_hot_path_branch() -> None:
    """Select the Python backend once when fastbloom-rs is absent."""
    factory = BloomFilterFactory(importer=_MissingNativeImporter())
    bloom = factory.create(size=1_000, expected=100)
    assert factory.backend_name == "python"
    assert bloom.backend_name == "python"
    assert bloom.algorithm_name == "xxh3-km-v1"


def test_default_dimensions_target_about_one_percent_false_positives() -> None:
    """Keep framework defaults useful instead of allocating one bit per item."""
    settings = SettingsInfo()
    bloom = PythonBloomFilter(
        size=settings.BLOOM_INFO.SIZE,
        expected=settings.BLOOM_INFO.EXPECTED,
    )
    bloom.inserted = settings.BLOOM_INFO.EXPECTED
    assert bloom.get_hash_count() == 7
    assert bloom.estimated_false_positive_rate() == pytest.approx(
        0.008193722,
        rel=1e-5,
    )


@pytest.mark.parametrize(
    "bloom_info",
    [
        {"SIZE": 0},
        {"EXPECTED": 0},
        {"HASH_COUNT": -1},
    ],
)
def test_settings_reject_invalid_bloom_dimensions(
    bloom_info: Dict[str, int],
) -> None:
    """Reject dimensions that cannot define a valid Bloom bitmap."""
    with pytest.raises(ValidationError):
        SettingsInfo(BLOOM_INFO=bloom_info)


def test_rust_and_python_indices_match_when_native_is_installed() -> None:
    """Require optional native workers to share the exact Redis indices."""
    factory = BloomFilterFactory()
    if factory.backend_name != "rust":
        return
    native = factory.create(size=10_000, expected=1_000, hash_count=7)
    portable = PythonBloomFilter(size=10_000, expected=1_000, hash_count=7)
    assert native.get_indices(b"scrapy-cffi") == portable.get_indices(
        b"scrapy-cffi"
    )


def test_redis_bloom_versions_keys_and_routes_mark_sent_consistently() -> None:
    """Isolate old bitmaps and use identical routing for check and mark."""
    repository = _FakeRedisRepository()
    settings = SettingsInfo()
    settings.BLOOM_INFO.SIZE = 10_000
    settings.BLOOM_INFO.EXPECTED = 1_000
    settings.BLOOM_INFO.HASH_COUNT = 7
    bloom = RedisBloomDupeFilter(
        settings=settings,
        redis_repository=repository,
        redis_namespace="demo",
    )
    request = HttpRequest(url="https://example.com/path")
    asyncio.run(bloom.request_seen(request, spider=None))
    assert repository.last_filter is not None
    new_key, sent_key, indices = repository.last_filter
    assert new_key.endswith(":demo:xxh3-km-v1")
    assert sent_key.endswith(":demo:xxh3-km-v1")
    asyncio.run(bloom.mark_sent(request, spider=None))
    assert repository.last_pipeline is not None
    assert repository.last_pipeline.operations == [
        (sent_key, index, 1) for index in indices
    ]
