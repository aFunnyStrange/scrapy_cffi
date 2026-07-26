from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


class FakeRedis:
    redis_mode = "single"
    _redis_url = []

    def __init__(self):
        self.hashes = {}
        self.queues = {}

    async def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value
        return 1

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def rpush(self, key, value):
        self.queues.setdefault(key, []).append(value)
        return len(self.queues[key])


class FakeKafka:
    def __init__(self):
        self.topics = {}
        self.calls = []
        self.acked = []
        self.next_offset = 0

    async def produce(self, topic, message, key=None):
        record = SimpleNamespace(
            topic=topic,
            consumer_group=None,
            partition=0,
            offset=self.next_offset,
            value=message,
        )
        self.next_offset += 1
        self.topics.setdefault(topic, []).append(record)
        self.calls.append(("produce", topic, key))
        return record

    async def dequeue_request(self, topic, consumer_group, **kwargs):
        self.calls.append(("dequeue", topic, consumer_group))
        queue = self.topics.get(topic, [])
        if not queue:
            return None
        record = queue.pop(0)
        record.consumer_group = consumer_group
        return record

    async def ack_request(self, message):
        self.acked.append(message)
        return True

    async def delete_topics(self, topics):
        for topic in topics:
            self.topics.pop(topic, None)


class FakeRabbit:
    def __init__(self):
        self.queues = {}

    async def rpush(self, queue_name, message):
        self.queues.setdefault(queue_name, []).append(message)
        return True

    async def dequeue_request(self, queue_name):
        queue = self.queues.get(queue_name, [])
        return queue.pop(0) if queue else None

    async def llen(self, queue_name):
        return len(self.queues.get(queue_name, []))

    async def delete_queue(self, queue_name):
        self.queues.pop(queue_name, None)
        return True


class Spider:
    name = "demo"
    kafka_topic = "demo.requests"
    kafka_start_topic = "demo.start"
    kafka_group = None
    kafka_start_group = None


def _scheduler(settings, sessions, redis, kafka):
    from scrapy_cffi.core.scheduler.kafka import KafkaScheduler

    return KafkaScheduler(
        spiders_name=["demo"],
        stop_event=asyncio.Event(),
        settings=settings,
        sessions=sessions,
        sessions_lock=asyncio.Lock(),
        signalManager=MagicMock(),
        redisManager=redis,
        kafkaManager=kafka,
    )


def test_kafka_work_and_start_topics_are_separate_and_manually_acked():
    from scrapy_cffi.core.downloader.internet import HttpRequest
    from scrapy_cffi.core.sessions import SessionManager
    from scrapy_cffi.settings import SettingsInfo

    async def run():
        settings = SettingsInfo(SCHEDULER_PERSIST=True)
        settings.KAFKA_INFO.URL = "127.0.0.1:9092"
        redis = FakeRedis()
        kafka = FakeKafka()
        source_sessions = SessionManager(asyncio.Event(), settings)
        source_sessions.get_or_create_session("account").session.cookies.set("token", "fresh")
        source = _scheduler(settings, source_sessions, redis, kafka)

        request = HttpRequest(
            session_id="account",
            url="https://example.com/page",
            dont_filter=True,
        )
        assert await source.put(request, Spider())
        assert len(kafka.topics["demo.requests"]) == 1
        assert "demo.start" not in kafka.topics

        target_sessions = SessionManager(asyncio.Event(), settings)
        target = _scheduler(settings, target_sessions, redis, kafka)
        leased = await target.get(Spider())
        assert leased.url == request.url
        assert not kafka.acked
        assert target_sessions.get_session_cookies("account") == {
            "account": {"token": "fresh"}
        }
        await target.complete_request(leased, Spider())
        assert len(kafka.acked) == 1

        await kafka.produce("demo.start", b"https://example.com/start")
        start_message = await target.get_start_req(Spider())
        assert start_message.value == b"https://example.com/start"
        assert kafka.calls[-1][1] == "demo.start"
        start_request = HttpRequest(
            url=start_message.value.decode(),
            dont_filter=True,
            meta={"is_start_url": True},
        )
        target.attach_start_req(start_request, start_message)
        assert len(kafka.acked) == 1
        assert await target.put(start_request, Spider())
        assert len(kafka.acked) == 2

        await source_sessions.close_all()
        await target_sessions.close_all()

    asyncio.run(run())


def test_kafka_topic_waits_for_partition_leaders_and_full_isr():
    from scrapy_cffi.mq.kafka import KafkaManager

    async def run():
        manager = object.__new__(KafkaManager)
        manager.loop = asyncio.get_running_loop()
        manager._client_kwargs = {"request_timeout_ms": 1000}
        admin = SimpleNamespace(
            describe_topics=AsyncMock(
                side_effect=[
                    [
                        {
                            "topic": "requests",
                            "error_code": 0,
                            "partitions": [
                                {"leader": -1, "isr": []},
                            ],
                        }
                    ],
                    [
                        {
                            "topic": "requests",
                            "error_code": 0,
                            "partitions": [
                                {
                                    "leader": 1,
                                    "replicas": [1, 2, 3],
                                    "isr": [1],
                                },
                            ],
                        }
                    ],
                ]
            )
        )

        await manager._wait_topic_ready(
            admin,
            "requests",
            num_partitions=1,
            replication_factor=3,
        )
        assert admin.describe_topics.await_count == 2

    asyncio.run(run())


def test_redis_scheduler_requeues_unfinished_request_for_ctrl_c():
    from scrapy_cffi.core.downloader.internet import HttpRequest
    from scrapy_cffi.core.scheduler.redis import RedisScheduler
    from scrapy_cffi.core.sessions import SessionManager
    from scrapy_cffi.settings import SettingsInfo

    class QueueRedis(FakeRedis):
        async def dequeue_request(self, queue_key):
            queue = self.queues.get(queue_key, [])
            return queue.pop(0) if queue else None

        async def llen(self, key):
            return len(self.queues.get(key, []))

    async def run():
        settings = SettingsInfo(SCHEDULER_PERSIST=True)
        redis = QueueRedis()
        sessions = SessionManager(asyncio.Event(), settings)
        scheduler = RedisScheduler(
            spiders_name=["demo"],
            stop_event=asyncio.Event(),
            settings=settings,
            sessions=sessions,
            sessions_lock=asyncio.Lock(),
            signalManager=MagicMock(),
            redisManager=redis,
        )
        request = HttpRequest(url="https://example.com", dont_filter=True)
        assert await scheduler.put(request, Spider())
        leased = await scheduler.get(Spider())
        assert not redis.queues["demo_req"]
        assert await scheduler.requeue_inflight(Spider()) == 1
        assert len(redis.queues["demo_req"]) == 1
        await scheduler.complete_request(leased, Spider())

        start_request = HttpRequest(url="https://example.com/start", dont_filter=True)
        scheduler.attach_start_req(start_request, b"https://example.com/start")
        assert await scheduler.requeue_inflight(Spider()) == 1
        assert redis.queues["demo_redis_start"] == [b"https://example.com/start"]
        await sessions.close_all()

    asyncio.run(run())


def test_rabbit_scheduler_requeues_work_and_start_requests_for_ctrl_c():
    from scrapy_cffi.core.downloader.internet import HttpRequest
    from scrapy_cffi.core.scheduler.rabbitmq import RabbitMqScheduler
    from scrapy_cffi.core.sessions import SessionManager
    from scrapy_cffi.settings import SettingsInfo

    class RabbitSpider:
        name = "rabbit"
        rabbitmq_queue = "rabbit.start"

    async def run():
        settings = SettingsInfo(SCHEDULER_PERSIST=True)
        redis = FakeRedis()
        rabbit = FakeRabbit()
        sessions = SessionManager(asyncio.Event(), settings)
        scheduler = RabbitMqScheduler(
            spiders_name=["rabbit"],
            stop_event=asyncio.Event(),
            settings=settings,
            sessions=sessions,
            sessions_lock=asyncio.Lock(),
            signalManager=MagicMock(),
            redisManager=redis,
            rabbitmqManager=rabbit,
        )
        request = HttpRequest(url="https://example.com", dont_filter=True)
        assert await scheduler.put(request, RabbitSpider())
        leased = await scheduler.get(RabbitSpider())
        scheduler.attach_start_req(
            HttpRequest(url="https://example.com/start"),
            b"https://example.com/start",
        )
        assert await scheduler.requeue_inflight(RabbitSpider()) == 2
        assert len(rabbit.queues["rabbit_req"]) == 1
        assert rabbit.queues["rabbit.start"] == [b"https://example.com/start"]
        await scheduler.complete_request(leased, RabbitSpider())
        await sessions.close_all()

    asyncio.run(run())


def test_rabbit_and_kafka_nonpersistent_cleanup_keeps_redis_dedup_required():
    from scrapy_cffi.core.scheduler.kafka import KafkaScheduler
    from scrapy_cffi.core.scheduler.rabbitmq import RabbitMqScheduler
    from scrapy_cffi.core.sessions import SessionManager
    from scrapy_cffi.settings import SettingsInfo

    async def run():
        settings = SettingsInfo(SCHEDULER_PERSIST=False)
        settings.KAFKA_INFO.URL = "127.0.0.1:9092"
        sessions = SessionManager(asyncio.Event(), settings)

        for scheduler_cls, manager_kw in (
            (RabbitMqScheduler, {"rabbitmqManager": FakeRabbit()}),
            (KafkaScheduler, {"kafkaManager": FakeKafka()}),
        ):
            try:
                scheduler_cls(
                    spiders_name=["demo"],
                    stop_event=asyncio.Event(),
                    settings=settings,
                    sessions=sessions,
                    sessions_lock=asyncio.Lock(),
                    signalManager=MagicMock(),
                    redisManager=None,
                    **manager_kw,
                )
            except ValueError as exc:
                assert "RedisScheduler requires" in str(exc)
            else:
                raise AssertionError("Distributed broker scheduler accepted no Redis")

        redis = FakeRedis()
        rabbit = FakeRabbit()
        rabbit.queues.update({"demo_req": [b"work"], "rabbit.start": [b"start"]})
        rabbit_scheduler = RabbitMqScheduler(
            spiders_name=["demo"],
            stop_event=asyncio.Event(),
            settings=settings,
            sessions=sessions,
            sessions_lock=asyncio.Lock(),
            signalManager=MagicMock(),
            redisManager=redis,
            rabbitmqManager=rabbit,
        )

        class RabbitSpider:
            name = "demo"
            rabbitmq_queue = "rabbit.start"

        await rabbit_scheduler.cleanup(RabbitSpider())
        assert rabbit.queues == {}

        kafka = FakeKafka()
        kafka.topics.update({"demo.requests": [b"work"], "demo.start": [b"start"]})
        kafka_scheduler = _scheduler(settings, sessions, redis, kafka)
        await kafka_scheduler.cleanup(Spider())
        assert kafka.topics == {}
        await sessions.close_all()

    asyncio.run(run())


def test_kafka_offsets_commit_only_after_contiguous_completion():
    import sys

    if "aiokafka" not in sys.modules:
        aiokafka = MagicMock()
        aiokafka.AIOKafkaProducer = MagicMock
        aiokafka.AIOKafkaConsumer = MagicMock
        admin = MagicMock()
        admin.AIOKafkaAdminClient = MagicMock
        admin.NewTopic = MagicMock
        errors = MagicMock()
        errors.KafkaConnectionError = ConnectionError
        errors.TopicAlreadyExistsError = type("TopicAlreadyExistsError", (Exception,), {})
        structs = MagicMock()
        structs.TopicPartition = lambda topic, partition: (topic, partition)
        structs.OffsetAndMetadata = lambda offset, metadata: (offset, metadata)
        sys.modules["aiokafka"] = aiokafka
        sys.modules["aiokafka.admin"] = admin
        sys.modules["aiokafka.errors"] = errors
        sys.modules["aiokafka.structs"] = structs

    from scrapy_cffi.mq.kafka import KafkaManager, KafkaMessage

    async def run():
        manager = KafkaManager(asyncio.Event(), "127.0.0.1:9092")
        consumer = MagicMock()
        consumer.commit = AsyncMock()
        manager._consumers[("work", "group")] = consumer
        manager._pending_offsets[("work", "group", 0)] = deque(
            [[10, False], [11, False]]
        )
        later = KafkaMessage("work", "group", 0, 11, b"later")
        earlier = KafkaMessage("work", "group", 0, 10, b"earlier")

        assert await manager.ack_request(later)
        consumer.commit.assert_not_awaited()
        assert await manager.ack_request(earlier)
        consumer.commit.assert_awaited_once_with({("work", 0): (12, "")})

    asyncio.run(run())


def test_crawler_shutdown_cancels_then_requeues_then_snapshots_before_stop():
    from scrapy_cffi.crawler import Crawler
    from scrapy_cffi.settings import SettingsInfo

    async def run():
        events = []

        class Sessions:
            def freeze(self):
                events.append("freeze")

            async def close_all(self):
                events.append("close_sessions")

        class ManagedTasks:
            tasks_done_event = asyncio.Event()
            error_event = asyncio.Event()

            async def cancel_all(self):
                events.append("cancel")

        class Scheduler:
            is_distributed = True

            async def requeue_inflight(self, spider):
                assert not crawler.stop_event.is_set()
                events.append("requeue")

            async def persist_all_sessions(self, spider):
                assert not crawler.stop_event.is_set()
                events.append("snapshot")

        crawler = Crawler()
        crawler.settings = SettingsInfo(SCHEDULER_PERSIST=True)
        crawler.stop_event = asyncio.Event()
        crawler.sessions = Sessions()
        crawler.taskManager = ManagedTasks()
        crawler.engines = [SimpleNamespace(taskManager=crawler.taskManager)]
        crawler.spiders = [SimpleNamespace(name="demo")]
        crawler.schedulers = {"demo": Scheduler()}
        redis_close = AsyncMock()
        mongodb_close = AsyncMock()
        crawler.redisManager = SimpleNamespace(close=redis_close)
        crawler.mongodbManager = SimpleNamespace(close=mongodb_close)
        crawler.signalManager = SimpleNamespace(stop=AsyncMock())
        crawler.rabbitmqManager = None
        crawler.kafkaManager = None
        crawler.mysqlManager = None
        crawler.postgresManager = None

        await crawler.shutdown()
        assert events[:4] == ["freeze", "cancel", "requeue", "snapshot"]
        assert crawler.stop_event.is_set()
        assert events[-1] == "close_sessions"
        redis_close.assert_awaited_once()
        mongodb_close.assert_awaited_once()

    asyncio.run(run())


def test_crawler_nonpersistent_cleanup_runs_once_before_broker_close():
    from scrapy_cffi.crawler import Crawler
    from scrapy_cffi.settings import SettingsInfo

    async def run():
        events = []

        class Sessions:
            def freeze(self):
                pass

            async def close_all(self):
                pass

        class ManagedTasks:
            tasks_done_event = asyncio.Event()
            error_event = asyncio.Event()

            async def cancel_all(self):
                pass

        class Scheduler:
            is_distributed = False
            dupefilter = None

            async def requeue_inflight(self, spider):
                pass

            async def cleanup(self, spider):
                assert not crawler.stop_event.is_set()
                events.append("cleanup")

        crawler = Crawler()
        crawler.settings = SettingsInfo(SCHEDULER_PERSIST=False)
        crawler.stop_event = asyncio.Event()
        crawler.sessions = Sessions()
        crawler.taskManager = ManagedTasks()
        crawler.engines = []
        crawler.spiders = [SimpleNamespace(name="demo")]
        crawler.schedulers = {"demo": Scheduler()}
        crawler.signalManager = SimpleNamespace(stop=AsyncMock())
        crawler.redisManager = SimpleNamespace(delete=AsyncMock(), close=AsyncMock())
        crawler.rabbitmqManager = SimpleNamespace(
            close=AsyncMock(side_effect=lambda: events.append("rabbit_close"))
        )
        crawler.kafkaManager = None
        crawler.mysqlManager = None
        crawler.postgresManager = None
        crawler.mongodbManager = None

        await crawler.shutdown()
        assert events == ["cleanup", "rabbit_close"]

    asyncio.run(run())


def test_crawler_redis_cleanup_survives_broker_cleanup_failure():
    from scrapy_cffi.crawler import Crawler
    from scrapy_cffi.settings import SettingsInfo

    async def run():
        events = []

        class Scheduler:
            async def cleanup(self, spider):
                events.append("broker_cleanup")
                if events.count("broker_cleanup") == 1:
                    raise RuntimeError("broker unavailable")

            async def cleanup_redis_state(self, spider):
                events.append("redis_cleanup")
                return 2

        crawler = Crawler()
        crawler.settings = SettingsInfo(SCHEDULER_PERSIST=False)
        crawler.spiders = [SimpleNamespace(name="demo")]
        crawler.schedulers = {"demo": Scheduler()}
        crawler.logger = SimpleNamespace(
            error=lambda *args, **kwargs: events.append("cleanup_error")
        )

        await crawler._cleanup_scheduler_state()
        assert events == [
            "broker_cleanup",
            "redis_cleanup",
            "cleanup_error",
        ]

        # A failed backend is retried, while Redis cleanup remains harmless.
        await crawler._cleanup_scheduler_state()
        assert events == [
            "broker_cleanup",
            "redis_cleanup",
            "cleanup_error",
            "broker_cleanup",
            "redis_cleanup",
        ]
        await crawler._cleanup_scheduler_state()
        assert events == [
            "broker_cleanup",
            "redis_cleanup",
            "cleanup_error",
            "broker_cleanup",
            "redis_cleanup",
        ]

    asyncio.run(run())


def test_rabbit_queue_declaration_is_stable_across_persist_modes():
    from scrapy_cffi.mq.rabbitmq import RabbitMQManager

    async def run():
        declarations = []

        class Queue:
            async def bind(self, exchange, routing_key):
                return None

        class Channel:
            async def declare_queue(self, name, **kwargs):
                declarations.append((name, kwargs))
                return Queue()

        for persist in (False, True):
            manager = RabbitMQManager(
                stop_event=asyncio.Event(),
                rabbitmq_url="amqp://guest:guest@127.0.0.1:5672/",
                persist=persist,
            )
            manager._channel = Channel()
            manager._exchange = object()
            await manager.declare_queue("shared")

        assert declarations == [
            ("shared", {"durable": True, "auto_delete": False}),
            ("shared", {"durable": True, "auto_delete": False}),
        ]

    asyncio.run(run())


def test_rabbit_dequeue_cancellation_settles_rpc_and_requeues_delivery():
    from scrapy_cffi.mq.rabbitmq import RabbitMQManager

    async def run():
        get_started = asyncio.Event()
        finish_get = asyncio.Event()
        rejected = []

        class Message:
            async def reject(self, requeue):
                rejected.append(requeue)

        class Queue:
            async def get(self, timeout, fail):
                assert timeout == 1.0
                assert fail is False
                get_started.set()
                await finish_get.wait()
                return Message()

        manager = RabbitMQManager(
            stop_event=asyncio.Event(),
            rabbitmq_url="amqp://guest:guest@127.0.0.1:5672/",
            persist=False,
        )
        manager._exchange = object()
        manager._consumer_queues["shared"] = Queue()

        task = asyncio.create_task(
            manager.dequeue_request("shared", timeout=30)
        )
        await get_started.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        finish_get.set()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("dequeue must propagate cancellation")
        assert rejected == [True]

    asyncio.run(run())


def test_crawler_shutdown_preparation_is_atomic_when_callers_race():
    from scrapy_cffi.crawler import Crawler
    from scrapy_cffi.settings import SettingsInfo

    async def run():
        events = []

        class Sessions:
            def freeze(self):
                events.append("freeze")

        class ManagedTasks:
            async def cancel_all(self):
                events.append("cancel")
                await asyncio.sleep(0)

        class Scheduler:
            async def requeue_inflight(self, spider):
                assert not crawler.stop_event.is_set()
                events.append("requeue")
                await asyncio.sleep(0)

        crawler = Crawler()
        crawler.settings = SettingsInfo(SCHEDULER_PERSIST=False)
        crawler.stop_event = asyncio.Event()
        crawler.sessions = Sessions()
        crawler.engines = [SimpleNamespace(taskManager=ManagedTasks())]
        crawler.spiders = [SimpleNamespace(name="demo")]
        crawler.schedulers = {"demo": Scheduler()}
        crawler.redisManager = None

        await asyncio.gather(
            crawler._prepare_shutdown(),
            crawler._prepare_shutdown(),
        )
        assert events == ["freeze", "cancel", "requeue"]
        assert crawler.stop_event.is_set()

    asyncio.run(run())


def test_cancelled_callback_does_not_ack_broker_request():
    from scrapy_cffi.core.engine import Engine

    async def run():
        scheduler = SimpleNamespace(complete_request=AsyncMock())
        engine = Engine.__new__(Engine)
        engine.scheduler = scheduler

        async def slow_output():
            await asyncio.sleep(30)
            yield {"never": True}

        source_request = object()
        task = asyncio.create_task(
            engine.get_spider_output(slow_output(), source_request=source_request)
        )
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        scheduler.complete_request.assert_not_awaited()

    asyncio.run(run())
