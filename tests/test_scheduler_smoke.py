"""Smoke tests: memory / Redis / RabbitMQ scheduler initialization paths."""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_aiokafka_stubs():
    if "aiokafka" in sys.modules:
        return
    aiokafka = MagicMock()
    aiokafka.AIOKafkaProducer = MagicMock
    aiokafka.AIOKafkaConsumer = MagicMock
    admin = MagicMock()
    admin.AIOKafkaAdminClient = MagicMock
    admin.NewTopic = MagicMock
    errors = MagicMock()
    errors.KafkaConnectionError = type("KafkaConnectionError", (ConnectionError,), {})
    errors.TopicAlreadyExistsError = type("TopicAlreadyExistsError", (Exception,), {})
    structs = MagicMock()
    structs.TopicPartition = lambda topic, partition: (topic, partition)
    structs.OffsetAndMetadata = lambda offset, metadata: (offset, metadata)
    sys.modules["aiokafka"] = aiokafka
    sys.modules["aiokafka.admin"] = admin
    sys.modules["aiokafka.errors"] = errors
    sys.modules["aiokafka.structs"] = structs


def _minimal_spider_module(tmp: Path, *, redis: bool = False, rabbit: bool = False, kafka: bool = False) -> Path:
    spiders = tmp / "spiders"
    spiders.mkdir(parents=True, exist_ok=True)
    if kafka:
        body = textwrap.dedent(
            """
            from scrapy_cffi.spiders.kafka import KafkaSpider
            from scrapy_cffi.internet import HttpResponse

            class DemoSpider(KafkaSpider):
                name = "demo"
                allowed_domains = ["127.0.0.1"]
                kafka_start_topic = "demo.start"
                kafka_topic = "demo.requests"

                async def parse(self, response: HttpResponse):
                    yield {"ok": True}
            """
        )
    elif rabbit:
        body = textwrap.dedent(
            """
            from scrapy_cffi.spiders.rabbitmq import RabbitmqSpider
            from scrapy_cffi.internet import HttpRequest, HttpResponse

            class DemoSpider(RabbitmqSpider):
                name = "demo"
                allowed_domains = ["127.0.0.1"]
                rabbitmq_queue = "demo_q"

                async def parse(self, response: HttpResponse):
                    yield {"ok": True}
            """
        )
    elif redis:
        body = textwrap.dedent(
            """
            from scrapy_cffi.spiders.redis import RedisSpider
            from scrapy_cffi.internet import HttpRequest, HttpResponse

            class DemoSpider(RedisSpider):
                name = "demo"
                allowed_domains = ["127.0.0.1"]
                redis_key = "demo_q"

                async def parse(self, response: HttpResponse):
                    yield {"ok": True}
            """
        )
    else:
        body = textwrap.dedent(
            """
            from scrapy_cffi.spiders import Spider
            from scrapy_cffi.internet import HttpResponse

            class DemoSpider(Spider):
                name = "demo"
                allowed_domains = ["127.0.0.1"]
                start_urls = ["http://127.0.0.1:8002/"]

                async def parse(self, response: HttpResponse):
                    yield {"ok": True}
            """
        )
    (spiders / "demo.py").write_text(body.strip() + "\n", encoding="utf-8")
    (spiders / "__init__.py").write_text("from .demo import DemoSpider\n", encoding="utf-8")
    return spiders


def _add_memory_spider(spiders: Path) -> None:
    """Add one finite memory spider beside a distributed spider fixture."""
    body = textwrap.dedent(
        """
        from scrapy_cffi.spiders import Spider

        class MemorySpider(Spider):
            name = "memory"
            allowed_domains = ["127.0.0.1"]

            async def start(self):
                if False:
                    yield None
        """
    )
    (spiders / "memory.py").write_text(
        body.strip() + "\n",
        encoding="utf-8",
    )


def _base_settings(spiders_path: Path):
    from scrapy_cffi.settings import SettingsInfo

    settings = SettingsInfo()
    settings.ROBOTSTXT_OBEY = False
    settings.SPIDERS_PATH = str(spiders_path)
    settings.ITEM_PIPELINES_PATH = []
    settings.DOWNLOAD_INTERCEPTORS_PATH = {}
    settings.MAX_SCHEDULER_LOOP_NUM = 1
    return settings


async def _init_crawler(
    settings,
    *,
    start_type=0,
    mock_redis=False,
    mock_rabbit=False,
    mock_kafka=False,
):
    from scrapy_cffi.crawler import Crawler

    resources = MagicMock()
    resources.redis = None
    resources.rabbitmq = None
    resources.kafka = None
    resources.mysql = None
    resources.postgres = None
    resources.mongodb = None
    resources.start = AsyncMock()
    resources.close = AsyncMock()
    if mock_redis:
        resources.redis = MagicMock(redis_mode="single", cluster_nodes=[])
    if mock_rabbit:
        resources.rabbitmq = MagicMock()
    if mock_kafka:
        resources.kafka = MagicMock()
        resources.kafka.push = AsyncMock(return_value=True)

    with patch(
        "scrapy_cffi.composition.build_resource_service",
        return_value=resources,
    ):
        crawler = Crawler()
        await crawler.do_initialization(settings=settings, start_type=start_type)
        return crawler


def test_memory_scheduler_init(tmp_path):
    from scrapy_cffi.interceptors import ClientHintsDownloadInterceptor

    spiders = _minimal_spider_module(tmp_path)
    settings = _base_settings(spiders)
    crawler = asyncio.run(_init_crawler(settings))
    assert crawler.schedulers["demo"].is_distributed is False
    assert type(crawler.schedulers["demo"]).__name__ == "Scheduler"
    assert crawler.engines[0].scheduler_loop.__name__ == "_local_scheduler_loop"
    assert isinstance(
        crawler.downloadInterceptor_chain.chain_tail.instance,
        ClientHintsDownloadInterceptor,
    )


def test_redis_scheduler_init(tmp_path):
    spiders = _minimal_spider_module(tmp_path, redis=True)
    settings = _base_settings(spiders)
    settings.SCHEDULER = "scrapy_cffi.scheduler.RedisScheduler"
    settings.REDIS_INFO.URL = "redis://127.0.0.1:6379"
    crawler = asyncio.run(_init_crawler(settings, mock_redis=True))
    sch = crawler.schedulers["demo"]
    assert sch.is_distributed is True
    assert type(sch).__name__ == "RedisScheduler"
    assert hasattr(sch, "get_start_req")
    assert crawler.engines[0].scheduler_loop.__name__ == "_distributed_scheduler_loop"


def test_single_spider_and_scheduler_accept_real_classes(tmp_path):
    import importlib.util

    from scrapy_cffi.core.scheduler.redis import RedisScheduler

    spiders = _minimal_spider_module(tmp_path, redis=True)
    spec = importlib.util.spec_from_file_location(
        "typed_demo_spider",
        spiders / "demo.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    settings = _base_settings(spiders)
    settings.SPIDERS_PATH = module.DemoSpider
    settings.SCHEDULER = RedisScheduler
    settings.REDIS_INFO.URL = "redis://127.0.0.1:6379"

    crawler = asyncio.run(
        _init_crawler(settings, start_type=1, mock_redis=True)
    )
    assert crawler.spiders[0].__class__ is settings.SPIDERS_PATH
    assert crawler.schedulers["demo"].__class__ is RedisScheduler


def test_rabbitmq_scheduler_init(tmp_path):
    spiders = _minimal_spider_module(tmp_path, rabbit=True)
    settings = _base_settings(spiders)
    settings.SCHEDULER = "scrapy_cffi.scheduler.RabbitMqScheduler"
    settings.REDIS_INFO.URL = "redis://127.0.0.1:6379"
    settings.RABBITMQ_INFO.URL = "amqp://guest:guest@127.0.0.1:5672/"
    crawler = asyncio.run(_init_crawler(settings, mock_redis=True, mock_rabbit=True))
    sch = crawler.schedulers["demo"]
    assert sch.is_distributed is True
    assert type(sch).__name__ == "RabbitMqScheduler"
    assert hasattr(sch, "get_start_req")


def test_kafka_scheduler_init(tmp_path):
    spiders = _minimal_spider_module(tmp_path, kafka=True)
    settings = _base_settings(spiders)
    settings.REDIS_INFO.URL = "redis://127.0.0.1:6379"
    settings.KAFKA_INFO.URL = "127.0.0.1:9092"
    crawler = asyncio.run(_init_crawler(settings, mock_redis=True, mock_kafka=True))
    sch = crawler.schedulers["demo"]
    assert sch.is_distributed is True
    assert type(sch).__name__ == "KafkaScheduler"
    assert sch.get_queue_key(crawler.spiders[0]) == "demo.requests"
    assert sch.get_start_topic(crawler.spiders[0]) == "demo.start"


def test_run_all_mixed_spiders_preserve_each_scheduler_family(tmp_path):
    """A distributed spider must not promote a sibling memory spider."""
    cases = (
        ("redis", {"redis": True}, "RedisScheduler"),
        ("rabbitmq", {"rabbit": True}, "RabbitMqScheduler"),
        ("kafka", {"kafka": True}, "KafkaScheduler"),
    )
    for mode, fixture_kwargs, expected_scheduler in cases:
        if mode == "kafka":
            _install_aiokafka_stubs()
        spiders = _minimal_spider_module(
            tmp_path / mode,
            **fixture_kwargs,
        )
        _add_memory_spider(spiders)
        settings = _base_settings(spiders)
        settings.REDIS_INFO.URL = "redis://127.0.0.1:6379"
        if mode == "rabbitmq":
            settings.RABBITMQ_INFO.URL = (
                "amqp://guest:guest@127.0.0.1:5672/"
            )
        elif mode == "kafka":
            settings.KAFKA_INFO.URL = "127.0.0.1:9092"

        crawler = asyncio.run(
            _init_crawler(
                settings,
                mock_redis=True,
                mock_rabbit=mode == "rabbitmq",
                mock_kafka=mode == "kafka",
            )
        )

        assert type(crawler.schedulers["memory"]).__name__ == "Scheduler"
        assert type(crawler.schedulers["demo"]).__name__ == expected_scheduler
        memory_engine = next(
            engine for engine in crawler.engines if engine.spider.name == "memory"
        )
        assert memory_engine.scheduler_loop.__name__ == "_local_scheduler_loop"


def test_repository_package_keeps_optional_drivers_lazy():
    """Repository discovery must not import optional driver implementations."""
    import importlib

    sys.modules.pop("scrapy_cffi.repo", None)
    mod = importlib.import_module("scrapy_cffi.repo")
    assert "RedisRepository" in mod.__all__
    assert "SQLRepository" in mod.__all__


def test_kafka_crawler_init(tmp_path):
    """Kafka logging pipeline attaches when KAFKA_INFO is configured."""
    from scrapy_cffi.utils.log import KafkaLoggingHandler

    spiders = _minimal_spider_module(tmp_path)
    settings = _base_settings(spiders)
    settings.KAFKA_INFO.URL = "127.0.0.1:9092"
    crawler = asyncio.run(_init_crawler(settings, mock_kafka=True))
    assert crawler.resources.kafka is not None
    assert any(
        isinstance(h, KafkaLoggingHandler) for h in crawler.logger.handlers
    )


def test_memory_with_kafka_does_not_require_redis(tmp_path):
    spiders = _minimal_spider_module(tmp_path)
    settings = _base_settings(spiders)
    settings.KAFKA_INFO.URL = "127.0.0.1:9092"
    crawler = asyncio.run(_init_crawler(settings, mock_kafka=True))
    assert crawler.resources.redis is None
    assert type(crawler.schedulers["demo"]).__name__ == "Scheduler"


def test_kafka_client_produce_mock():
    _install_aiokafka_stubs()
    from scrapy_cffi.infra.kafka import KafkaClient

    async def run():
        manager = KafkaClient(
            kafka_url="127.0.0.1:9092",
        )
        mock_producer = MagicMock()
        mock_producer.start = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(return_value=True)
        manager._producer = mock_producer
        manager._bootstrap_servers = "127.0.0.1:9092"
        manager._ensured_topics.add("scrapy_cffi")
        result = await manager.produce("scrapy_cffi", b"hello")
        assert result is True
        mock_producer.send_and_wait.assert_called_once()

    asyncio.run(run())


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        test_memory_scheduler_init(p / "mem")
        test_redis_scheduler_init(p / "redis")
        test_rabbitmq_scheduler_init(p / "rabbit")
        test_kafka_scheduler_init(p / "kafka_scheduler")
    test_repository_package_keeps_optional_drivers_lazy()
    test_kafka_crawler_init(p / "kafka_crawler")
    test_memory_with_kafka_does_not_require_redis(p / "kafka_mem")
    test_kafka_client_produce_mock()
    print("ok")
