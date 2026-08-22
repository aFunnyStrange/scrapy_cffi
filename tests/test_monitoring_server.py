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

        assert snapshot.status == "running"
        assert workers[0].worker_id == "crawler-a"
        assert workers[0].spiders == ["orders"]
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


def test_monitor_extension_batches_hot_signals_without_background_task() -> None:
    """Publish lifecycle immediately while batching high-frequency counters."""

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
        assert not hasattr(extension, "_heartbeat_task")

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
