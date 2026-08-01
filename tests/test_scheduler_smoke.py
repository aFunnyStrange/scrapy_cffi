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


def _base_settings(spiders_path: Path):
    from scrapy_cffi.settings import SettingsInfo

    settings = SettingsInfo()
    settings.ROBOTSTXT_OBEY = False
    settings.SPIDERS_PATH = str(spiders_path)
    settings.ITEM_PIPELINES_PATH = []
    settings.DOWNLOAD_INTERCEPTORS_PATH = {}
    settings.MAX_SCHEDULER_LOOP_NUM = 1
    settings.SCHEDULER_LOOP_END = 0
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

    patches = []
    if mock_redis:
        mock_rm = MagicMock()
        mock_rm.from_crawler = MagicMock(return_value=mock_rm)
        patches.append(patch("scrapy_cffi.databases.redis.RedisManager.from_crawler", mock_rm.from_crawler))
    if mock_rabbit:
        aio_pika_mock = MagicMock()
        sys.modules.setdefault("aio_pika", aio_pika_mock)
        sys.modules.setdefault("aio_pika.exceptions", MagicMock())
        import scrapy_cffi.mq.rabbitmq as rabbit_mod

        mock_mq = MagicMock()
        mock_mq.from_crawler = MagicMock(return_value=mock_mq)
        patches.append(
            patch.object(rabbit_mod.RabbitMQManager, "from_crawler", mock_mq.from_crawler)
        )
    if mock_kafka:
        _install_aiokafka_stubs()
        import scrapy_cffi.mq.kafka as kafka_mod

        mock_km = MagicMock()
        mock_km.produce = AsyncMock(return_value=True)
        mock_km.produce_async = AsyncMock()
        mock_km.from_crawler = MagicMock(return_value=mock_km)
        patches.append(
            patch.object(kafka_mod.KafkaManager, "from_crawler", mock_km.from_crawler)
        )

    for p in patches:
        p.start()
    try:
        crawler = Crawler()
        await crawler.do_initialization(settings=settings, start_type=start_type)
        return crawler
    finally:
        for p in patches:
            p.stop()


def test_memory_scheduler_init(tmp_path):
    spiders = _minimal_spider_module(tmp_path)
    settings = _base_settings(spiders)
    crawler = asyncio.run(_init_crawler(settings))
    assert crawler.schedulers["demo"].is_distributed is False
    assert type(crawler.schedulers["demo"]).__name__ == "Scheduler"
    assert crawler.engines[0].scheduler_loop.__name__ == "_local_scheduler_loop"


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


def test_databases_lazy_sqlalchemy():
    """Redis import path must not require SQLAlchemy."""
    import importlib

    sys.modules.pop("scrapy_cffi.databases", None)
    mod = importlib.import_module("scrapy_cffi.databases")
    assert mod.RedisManager is not None
    # Lazy attr resolves only when accessed
    assert "SQLAlchemyMySQLManager" in mod.__all__


def test_kafka_crawler_init(tmp_path):
    """Kafka logging pipeline attaches when KAFKA_INFO is configured."""
    from scrapy_cffi.utils.log import KafkaLoggingHandler

    spiders = _minimal_spider_module(tmp_path)
    settings = _base_settings(spiders)
    settings.KAFKA_INFO.URL = "127.0.0.1:9092"
    crawler = asyncio.run(_init_crawler(settings, mock_kafka=True))
    assert crawler.kafkaManager is not None
    assert any(
        isinstance(h, KafkaLoggingHandler) for h in crawler.logger.handlers
    )


def test_memory_with_kafka_does_not_require_redis(tmp_path):
    spiders = _minimal_spider_module(tmp_path)
    settings = _base_settings(spiders)
    settings.KAFKA_INFO.URL = "127.0.0.1:9092"
    crawler = asyncio.run(_init_crawler(settings, mock_kafka=True))
    assert crawler.redisManager is None
    assert type(crawler.schedulers["demo"]).__name__ == "Scheduler"


def test_kafka_manager_produce_mock():
    _install_aiokafka_stubs()
    from scrapy_cffi.mq.kafka import KafkaManager

    async def run():
        manager = KafkaManager(
            stop_event=asyncio.Event(),
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
    test_databases_lazy_sqlalchemy()
    test_kafka_crawler_init(p / "kafka_crawler")
    test_memory_with_kafka_does_not_require_redis(p / "kafka_mem")
    test_kafka_manager_produce_mock()
    print("ok")
