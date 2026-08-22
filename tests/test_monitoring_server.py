"""Verify the opt-in crawler monitor wire contract and CLI binding."""

import asyncio
import builtins
import sys
from types import SimpleNamespace

import pytest

from scrapy_cffi.commands import server
from scrapy_cffi.commands.main import main
from scrapy_cffi.extensions.monitoring import CrawlerMonitorExtension
from scrapy_cffi.extensions.signal_manager import SignalManager
from scrapy_cffi.extensions.singal_info import SignalInfo
from scrapy_cffi.monitoring import MonitorEvent, MonitorStore, create_monitor_app
from scrapy_cffi.monitoring import TaskSnapshot
from scrapy_cffi.runtime import RunContext, RunState, WorkerAvailability, WorkerState
from scrapy_cffi.settings import SettingsInfo


def test_monitor_store_tracks_multiple_active_engines() -> None:
    """Do not mark a multi-spider worker stopped until its last engine exits."""

    async def exercise() -> None:
        """Record the lifecycle sequence on one event loop."""
        store = MonitorStore()
        for timestamp in (1.0, 2.0):
            await store.record(
                MonitorEvent(
                    worker_id="worker-1",
                    event="engine_started",
                    timestamp=timestamp,
                )
            )
        first_stop = await store.record(
            MonitorEvent(
                worker_id="worker-1",
                event="engine_stopped",
                timestamp=3.0,
            )
        )
        final_stop = await store.record(
            MonitorEvent(
                worker_id="worker-1",
                event="engine_stopped",
                timestamp=4.0,
            )
        )

        assert first_stop.status == "running"
        assert final_stop.status == "stopped"

    asyncio.run(exercise())


def test_signal_shutdown_drains_enqueued_monitor_events() -> None:
    """Use the explicit queue sentinel after all owned enqueue tasks finish."""

    async def exercise() -> None:
        """Stop immediately after enqueueing and retain the final callback."""
        stop_event = asyncio.Event()
        settings = SettingsInfo()
        manager = SignalManager(stop_event=stop_event, settings=settings)
        signal = object()
        received = []

        async def callback(data) -> None:
            """Capture the final lifecycle payload."""
            received.append(data.reason)

        manager.connect(signal, callback)
        manager.start()
        await manager._safe_put(signal, SignalInfo(reason="engine_stopped"))
        stop_event.set()
        await manager.stop()

        assert received == ["engine_stopped"]

    asyncio.run(exercise())


def test_monitor_app_registers_and_lists_crawlers() -> None:
    """Exercise the actual FastAPI routes used by monitoring extensions."""

    async def exercise() -> None:
        """Call the asynchronous endpoints registered on the real app."""
        app = create_monitor_app()
        endpoints = {route.path: route.endpoint for route in app.routes}
        snapshot = await endpoints["/api/v1/workers/events"](
            MonitorEvent(
                worker_id="crawler-a",
                event="spider_opened",
                timestamp=12.5,
                spider_name="orders",
                counters={"response_received": 3},
            )
        )
        workers = await endpoints["/api/v1/workers"]()
        runs = await endpoints["/api/v1/runs"]()

        assert snapshot.status == "running"
        assert workers[0].worker_id == "crawler-a"
        assert workers[0].spiders == ["orders"]
        assert runs == []
        assert await endpoints["/health"]() == {"status": "ok"}
        assert "Experimental" in await endpoints["/"]()

    asyncio.run(exercise())


def test_monitor_app_reports_optional_dependency_install_command(
    monkeypatch,
) -> None:
    """Fail only when the uninstalled server capability is selected."""
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        """Simulate a core-only environment for FastAPI imports."""
        if name == "fastapi" or name.startswith("fastapi."):
            raise ImportError("fastapi is intentionally unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    with pytest.raises(RuntimeError, match=r"scrapy_cffi\[server\]"):
        create_monitor_app()


def test_monitor_extension_batches_and_owns_heartbeat_task() -> None:
    """Publish lifecycle immediately and explicitly close the heartbeat."""

    async def exercise() -> None:
        """Drive lifecycle and hot callbacks directly."""
        callbacks = {}
        hooks = SimpleNamespace(
            signals=SimpleNamespace(
                connect=lambda signal, callback: callbacks.update(
                    {signal: callback}
                )
            )
        )
        logger = SimpleNamespace(warning=lambda *args: None)
        settings = SettingsInfo()
        settings.MONITOR_INFO.WORKER_ID = "worker-test"
        settings.MONITOR_INFO.EVENT_BATCH_SIZE = 2
        settings.MONITOR_INFO.HEARTBEAT_INTERVAL = 60.0
        run_context = RunContext(
            worker_id="context-worker",
            instance_id="instance-1",
            run_id="run-1",
            task_id="task-1",
        )
        hooks.run_context = run_context
        extension = CrawlerMonitorExtension.from_crawler(
            hooks,
            settings=settings,
            logger=logger,
        )
        published = []

        async def publish(event) -> None:
            """Capture one in-memory observation."""
            published.append(event)

        extension.client.publish = publish
        await extension.engine_started(SignalInfo(signal_time=1.0))
        await extension.response_received(SignalInfo(signal_time=2.0))
        await extension.response_received(SignalInfo(signal_time=3.0))

        assert [event.event for event in published] == [
            "engine_started",
            "counters_updated",
        ]
        assert published[-1].counters["response_received"] == 2
        assert published[0].instance_id == "instance-1"
        assert published[0].run_id == "run-1"
        assert published[0].task_id == "task-1"
        assert extension._heartbeat_task is not None
        await extension.engine_stopped(SignalInfo(signal_time=4.0))
        assert extension._heartbeat_task is None
        assert published[-1].run_state == RunState.COMPLETED

    asyncio.run(exercise())


def test_monitor_store_separates_errors_lifecycle_and_event_order() -> None:
    """Keep item errors observable without declaring the worker failed."""

    async def exercise() -> None:
        """Record ordered, stale, and terminal run facts."""
        store = MonitorStore()
        common = {
            "worker_id": "worker-1",
            "instance_id": "instance-1",
            "run_id": "run-1",
            "task_id": "task-1",
        }
        await store.record(
            MonitorEvent(
                **common,
                sequence=1,
                event="engine_started",
                timestamp=10.0,
                worker_state=WorkerState.RUNNING,
                run_state=RunState.RUNNING,
            )
        )
        error_snapshot = await store.record(
            MonitorEvent(
                **common,
                sequence=2,
                event="task_error",
                timestamp=11.0,
                detail="one request failed",
            )
        )
        stale_snapshot = await store.record(
            MonitorEvent(
                **common,
                sequence=1,
                event="run_failed",
                timestamp=9.0,
                run_state=RunState.FAILED,
            )
        )
        await store.record(
            MonitorEvent(
                **common,
                sequence=3,
                event="run_completed",
                timestamp=12.0,
                worker_state=WorkerState.STOPPED,
                run_state=RunState.COMPLETED,
            )
        )
        runs = await store.list_runs()

        assert error_snapshot.status == WorkerState.RUNNING
        assert stale_snapshot.last_event == "task_error"
        assert runs[0].state == RunState.COMPLETED
        assert runs[0].task_id == "task-1"

    asyncio.run(exercise())


def test_monitor_store_marks_only_availability_unreachable(monkeypatch) -> None:
    """A stale heartbeat must not invent stopped or failed lifecycle state."""

    async def exercise() -> None:
        """Advance observation time while retaining explicit run state."""
        clock = [10.0]
        monkeypatch.setattr(
            "scrapy_cffi.monitoring.store.time.time",
            lambda: clock[0],
        )
        store = MonitorStore(stale_after=5.0)
        await store.record(
            MonitorEvent(
                worker_id="worker-1",
                instance_id="instance-1",
                run_id="run-1",
                sequence=1,
                event="heartbeat",
                timestamp=10.0,
                worker_state=WorkerState.RUNNING,
                run_state=RunState.RUNNING,
            )
        )
        clock[0] = 20.0
        workers = await store.list_workers()
        runs = await store.list_runs()

        assert workers[0].availability == WorkerAvailability.UNREACHABLE
        assert workers[0].status == WorkerState.RUNNING
        assert runs[0].state == RunState.RUNNING

    asyncio.run(exercise())


def test_monitor_store_bounds_in_memory_history() -> None:
    """Evict old terminal observations without growing process memory forever."""

    async def exercise() -> None:
        """Record more terminal runs and workers than the configured bounds."""
        store = MonitorStore(max_workers=1, max_runs=1)
        for index in range(2):
            await store.record(
                MonitorEvent(
                    worker_id="worker-%s" % index,
                    instance_id="instance-%s" % index,
                    run_id="run-%s" % index,
                    sequence=1,
                    event="run_completed",
                    timestamp=float(index + 1),
                    worker_state=WorkerState.STOPPED,
                    run_state=RunState.COMPLETED,
                )
            )

        workers = await store.list_workers()
        runs = await store.list_runs()

        assert [worker.worker_id for worker in workers] == ["worker-1"]
        assert [run.run_id for run in runs] == ["run-1"]

    asyncio.run(exercise())


def test_monitor_app_uses_read_only_task_state_provider() -> None:
    """Display durable task facts without allowing the Hub to mutate them."""

    class Provider:
        """Return application-owned task snapshots for the test Hub."""

        async def list_tasks(self):
            """Return the bounded task list."""
            return [
                TaskSnapshot(
                    task_id="task-1",
                    state="retry",
                    updated_at=5.0,
                    run_id="run-1",
                )
            ]

        async def get_task(self, task_id):
            """Return the requested task when it matches."""
            tasks = await self.list_tasks()
            return tasks[0] if task_id == "task-1" else None

    async def exercise() -> None:
        """Call the provider-backed routes directly."""
        app = create_monitor_app(task_state_provider=Provider())
        endpoints = {route.path: route.endpoint for route in app.routes}

        tasks = await endpoints["/api/v1/tasks"]()
        task = await endpoints["/api/v1/tasks/{task_id}"]("task-1")

        assert tasks[0].state == "retry"
        assert task.task_id == "task-1"

    asyncio.run(exercise())


def test_server_cli_defaults_local_and_hub_binds_all_interfaces(
    monkeypatch,
) -> None:
    """Keep local binding safe unless the operator explicitly selects Hub mode."""
    calls = []
    monkeypatch.setattr(server, "run", lambda host, port: calls.append((host, port)))

    monkeypatch.setattr(sys, "argv", ["scrapy-cffi", "server"])
    assert main() is None
    monkeypatch.setattr(
        sys,
        "argv",
        ["scrapy-cffi", "server", "--hub", "--port", "7000"],
    )
    assert main() is None

    assert calls == [("127.0.0.1", 6800), ("0.0.0.0", 7000)]
