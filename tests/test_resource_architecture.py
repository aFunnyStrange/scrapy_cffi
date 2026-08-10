"""Verify infra, repository, service, and composition boundaries."""

import asyncio
from pathlib import Path
from unittest.mock import patch

from redis.exceptions import ConnectionError as RedisConnectionError

from scrapy_cffi.composition import build_resource_service
from scrapy_cffi.config import RedisInfo
from scrapy_cffi.infra.redis import RedisClient
from scrapy_cffi.settings import SettingsInfo


class FakeRedisClient:
    """Provide the Redis transport shape used by the composition test."""

    redis_mode = "single"
    cluster_nodes = []

    def __init__(self, available: bool) -> None:
        self.available = available
        self.closed = False

    async def connect(self) -> None:
        """Initialize the fake transport."""

    async def close(self) -> None:
        """Record transport closure."""
        self.closed = True

    async def rpush(self, key: str, value: bytes) -> int:
        """Fail the first generation and accept the replacement."""
        del key, value
        if not self.available:
            raise RedisConnectionError("redis unavailable")
        return 1


def test_composition_replaces_failed_redis_client_above_infra():
    """A repository retry replaces its client through the service-owned slot."""

    async def run() -> None:
        clients = []

        def factory(info: RedisInfo) -> FakeRedisClient:
            del info
            client = FakeRedisClient(available=bool(clients))
            clients.append(client)
            return client

        settings = SettingsInfo(
            REDIS_INFO=RedisInfo(URL="redis://127.0.0.1:6379/0"),
            INFRA_RETRY_ATTEMPTS=2,
            INFRA_RETRY_DELAY=0,
        )
        with patch.object(RedisClient, "from_info", side_effect=factory):
            resources = build_resource_service(settings, asyncio.Event())
            await resources.start()
            if resources.redis is None:
                raise AssertionError("Redis repository was not assembled")
            assert await resources.redis.rpush("requests", b"payload") == 1
            assert len(clients) == 2
            assert clients[0].closed is True
            await resources.close()
            assert clients[1].closed is True

    asyncio.run(run())


def test_infrastructure_has_no_retry_or_upper_layer_imports():
    """Concrete infrastructure must remain one-shot and dependency-inward."""
    package_root = Path(__file__).resolve().parents[1] / "scrapy_cffi"
    infra_files = list((package_root / "infra").rglob("*.py"))
    assert infra_files
    for path in infra_files:
        source = path.read_text(encoding="utf-8")
        assert "utils.reconnect" not in source
        assert "service.resilience" not in source
        assert "_reconnect_controller" not in source
        assert "def _reconnect" not in source


def test_legacy_database_and_mq_implementation_modules_are_removed():
    """The removed Manager packages must not regain implementation files."""
    package_root = Path(__file__).resolve().parents[1] / "scrapy_cffi"
    for legacy_name in ("databases", "mq"):
        legacy = package_root / legacy_name
        assert not list(legacy.glob("*.py"))
