import asyncio
import inspect

from scrapy_cffi.utils.reconnect import (
    AsyncReconnectController,
    reconnectable,
)


def test_concurrent_failures_share_one_reconnect():
    async def run():
        stop_event = asyncio.Event()
        state = {"connected": False, "reconnects": 0}

        async def reconnect():
            await asyncio.sleep(0)
            state["reconnects"] += 1
            state["connected"] = True

        controller = AsyncReconnectController(
            stop_event,
            reconnect,
            (ConnectionError,),
            label="test",
            retry_delay=0,
        )

        async def operation():
            if not state["connected"]:
                await asyncio.sleep(0)
                raise ConnectionError("offline")
            return "ok"

        results = await asyncio.gather(
            *[controller.run(operation) for _ in range(20)]
        )
        assert results == ["ok"] * 20
        assert state["reconnects"] == 1

    asyncio.run(run())


def test_stop_event_cancels_before_operation_or_reconnect():
    async def run():
        stop_event = asyncio.Event()
        stop_event.set()
        calls = {"operation": 0, "reconnect": 0}

        async def reconnect():
            calls["reconnect"] += 1

        async def operation():
            calls["operation"] += 1

        controller = AsyncReconnectController(
            stop_event,
            reconnect,
            (ConnectionError,),
            label="test",
            retry_delay=0,
        )
        try:
            await controller.run(operation)
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("stopped controller must cancel the operation")
        assert calls == {"operation": 0, "reconnect": 0}

    asyncio.run(run())


def test_reconnectable_preserves_explicit_method_signature():
    class ExampleManager:
        def __init__(self):
            self._reconnect_controller = AsyncReconnectController(
                asyncio.Event(),
                self._reconnect,
                (ConnectionError,),
                label="example",
                retry_delay=0,
            )

        async def _reconnect(self):
            return None

        @reconnectable
        async def fetch(self, key: str, limit: int = 1) -> bytes:
            return ("%s:%s" % (key, limit)).encode()

    signature = inspect.signature(ExampleManager.fetch)
    assert list(signature.parameters) == ["self", "key", "limit"]
    assert signature.return_annotation is bytes


def test_managers_do_not_intercept_all_attribute_access():
    import redis.asyncio as redis

    from scrapy_cffi.databases.redis import RedisManager
    from scrapy_cffi.databases.sqlalchemy_base import BaseSQLAlchemyManager
    from scrapy_cffi.mq.kafka import KafkaManager
    from scrapy_cffi.mq.rabbitmq import RabbitMQManager

    assert issubclass(RedisManager, redis.Redis)
    assert "__getattribute__" not in RedisManager.__dict__
    assert "__getattribute__" not in BaseSQLAlchemyManager.__dict__
    assert "__getattribute__" not in KafkaManager.__dict__
    assert "__getattribute__" not in RabbitMQManager.__dict__


def test_explicit_recovery_also_collapses_concurrent_callers():
    async def run():
        stop_event = asyncio.Event()
        reconnects = {"count": 0}

        async def reconnect():
            await asyncio.sleep(0)
            reconnects["count"] += 1

        controller = AsyncReconnectController(
            stop_event,
            reconnect,
            (ConnectionError,),
            label="loop",
            retry_delay=0,
        )
        observed_generation = controller.generation
        await asyncio.gather(
            *[controller.recover(observed_generation) for _ in range(20)]
        )
        assert reconnects["count"] == 1

    asyncio.run(run())
