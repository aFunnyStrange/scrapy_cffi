"""Verify resilience is owned above concrete infrastructure clients."""

import asyncio

from scrapy_cffi.service import ResourceSlot, RetryPolicy


class FakeResource:
    """Represent one replaceable transport generation."""

    def __init__(self, available: bool) -> None:
        self.available = available
        self.closed = False

    async def connect(self) -> None:
        """Initialize the fake transport."""

    async def close(self) -> None:
        """Record lifecycle closure."""
        self.closed = True

    async def read(self) -> str:
        """Return a result or simulate a transport outage."""
        if not self.available:
            await asyncio.sleep(0)
            raise ConnectionError("offline")
        return "ok"


def test_concurrent_failures_share_one_resource_replacement():
    """Concurrent observers of one generation trigger one replacement."""

    async def run() -> None:
        builds = {"count": 0}

        def factory() -> FakeResource:
            builds["count"] += 1
            return FakeResource(available=builds["count"] > 1)

        slot = ResourceSlot(factory)
        await slot.start()
        policy = RetryPolicy(
            asyncio.Event(),
            (ConnectionError,),
            max_attempts=3,
            retry_delay=0,
        )

        async def invoke() -> str:
            generation = slot.generation
            return await policy.run(
                lambda: slot.get().read(),
                lambda: slot.replace(generation),
            )

        results = await asyncio.gather(*(invoke() for _ in range(20)))
        assert results == ["ok"] * 20
        assert builds["count"] == 2
        await slot.close()

    asyncio.run(run())


def test_stop_event_cancels_before_operation_or_recovery():
    """A stopped runtime must not start an infrastructure call."""

    async def run() -> None:
        stop_event = asyncio.Event()
        stop_event.set()
        calls = {"operation": 0, "recover": 0}
        policy = RetryPolicy(stop_event, (ConnectionError,), retry_delay=0)

        async def operation() -> None:
            calls["operation"] += 1

        async def recover() -> None:
            calls["recover"] += 1

        try:
            await policy.run(operation, recover)
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Stopped policy must cancel the operation")
        assert calls == {"operation": 0, "recover": 0}

    asyncio.run(run())


def test_infrastructure_clients_do_not_own_retry_controllers():
    """Concrete adapters expose lifecycle but no retry or reconnect controller."""
    import redis.asyncio as redis

    from scrapy_cffi.infra.kafka import KafkaClient
    from scrapy_cffi.infra.rabbitmq import RabbitMQClient
    from scrapy_cffi.infra.redis import RedisClient
    from scrapy_cffi.infra.sqlalchemy import SqlAlchemyClient

    assert issubclass(RedisClient, redis.Redis)
    for client_type in (RedisClient, SqlAlchemyClient, KafkaClient, RabbitMQClient):
        assert "_reconnect_controller" not in client_type.__dict__
        assert "_reconnect" not in client_type.__dict__


def test_explicit_slot_replacement_collapses_concurrent_callers():
    """The resource slot serializes replacement independently of retry policy."""

    async def run() -> None:
        builds = {"count": 0}

        def factory() -> FakeResource:
            builds["count"] += 1
            return FakeResource(True)

        slot = ResourceSlot(factory)
        await slot.start()
        generation = slot.generation
        await asyncio.gather(*(slot.replace(generation) for _ in range(20)))
        assert builds["count"] == 2
        await slot.close()

    asyncio.run(run())


def test_failed_resource_close_does_not_block_replacement():
    """A broken old transport must not prevent constructing its replacement."""

    class CloseFailingResource(FakeResource):
        """Simulate a failed generation whose close call also fails."""

        async def close(self) -> None:
            """Raise the transport's close failure."""
            raise ConnectionError("close failed")

    async def run() -> None:
        """Replace the broken generation and verify the next one is usable."""
        builds = {"count": 0}

        def factory() -> FakeResource:
            """Return one broken generation followed by a healthy one."""
            builds["count"] += 1
            if builds["count"] == 1:
                return CloseFailingResource(False)
            return FakeResource(True)

        slot = ResourceSlot(factory)
        await slot.start()
        await slot.replace(slot.generation)
        assert await slot.get().read() == "ok"
        assert builds["count"] == 2
        await slot.close()

    asyncio.run(run())


def test_failed_replacement_connect_is_retried_before_next_operation():
    """Recovery retries client construction instead of calling an empty slot."""

    class ConnectFailingResource(FakeResource):
        """Simulate one resource generation that cannot connect."""

        async def connect(self) -> None:
            """Raise a retryable connection failure."""
            raise ConnectionError("connect failed")

    async def run() -> None:
        """Reach a healthy third generation through bounded recovery."""
        builds = {"count": 0}

        def factory() -> FakeResource:
            """Return failed operation, failed connection, then success."""
            builds["count"] += 1
            if builds["count"] == 1:
                return FakeResource(False)
            if builds["count"] == 2:
                return ConnectFailingResource(False)
            return FakeResource(True)

        slot = ResourceSlot(factory)
        await slot.start()
        policy = RetryPolicy(
            asyncio.Event(),
            (ConnectionError,),
            max_attempts=3,
            retry_delay=0,
        )

        async def operation() -> str:
            """Read from the current transport generation."""
            return await slot.get().read()

        observed = slot.generation
        result = await policy.run(
            operation,
            lambda: slot.replace(observed),
        )
        assert result == "ok"
        assert builds["count"] == 3
        await slot.close()

    asyncio.run(run())


def test_replacement_never_exposes_an_empty_resource_slot() -> None:
    """Concurrent operations retain a generation while replacement connects."""

    async def run() -> None:
        """Read the slot while a replacement is between construction and swap."""
        connect_release = asyncio.Event()
        replacement_connecting = asyncio.Event()
        builds = {"count": 0}

        class DelayedResource(FakeResource):
            """Pause only the replacement generation during connect."""

            async def connect(self) -> None:
                """Publish construction state and wait for the test owner."""
                if builds["count"] > 1:
                    replacement_connecting.set()
                    await connect_release.wait()

        def factory() -> FakeResource:
            """Create one initial and one delayed replacement resource."""
            builds["count"] += 1
            return DelayedResource(True)

        slot = ResourceSlot(factory)
        await slot.start()
        original = slot.get()
        replacement_task = asyncio.create_task(slot.replace(slot.generation))
        await replacement_connecting.wait()

        assert slot.get() is original

        connect_release.set()
        await replacement_task
        assert slot.get() is not original
        await slot.close()

    asyncio.run(run())
