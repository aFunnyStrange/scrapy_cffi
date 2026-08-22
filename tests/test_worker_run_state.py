"""Verify outer-scheduler run identity and normalized runtime outcomes."""

import asyncio
from types import SimpleNamespace

import pytest

from scrapy_cffi import CrawlerRunHandle, RunContext, RunState
from scrapy_cffi.crawler import Crawler
from scrapy_cffi.extensions import signals


def test_run_context_separates_process_run_and_business_identity() -> None:
    """Retain scheduler correlation fields without requiring a scheduler."""
    first = RunContext.create(task_id="task-1")
    second = RunContext.create(task_id="task-1")

    assert first.instance_id == second.instance_id
    assert first.run_id != second.run_id
    assert first.task_id == "task-1"


def test_crawler_run_handle_normalizes_success_failure_and_stop() -> None:
    """Return runtime outcomes while leaving business mapping to the caller."""

    async def exercise() -> None:
        """Drive handles with small in-memory tasks."""
        context = RunContext(
            instance_id="instance-1",
            run_id="run-1",
            task_id="task-1",
        )

        async def completed() -> None:
            """Complete one normal execution."""

        async def failed() -> None:
            """Raise one unhandled execution error."""
            raise ValueError("broken run")

        stop_called = asyncio.Event()

        async def shutdown() -> None:
            """Record application-owned shutdown invocation."""
            stop_called.set()

        crawler = SimpleNamespace(
            run_context=context,
            extensions_list=[],
            shutdown=shutdown,
        )
        success = CrawlerRunHandle(crawler, asyncio.create_task(completed()))
        failure = CrawlerRunHandle(crawler, asyncio.create_task(failed()))
        pending = CrawlerRunHandle(
            crawler,
            asyncio.create_task(asyncio.Event().wait()),
        )

        success_outcome = await success.wait()
        failure_outcome = await failure.wait()
        stopped_outcome = await pending.stop()

        assert success_outcome.state == RunState.COMPLETED
        assert failure_outcome.state == RunState.FAILED
        assert failure_outcome.error_type == "ValueError"
        assert stopped_outcome.state == RunState.CANCELLED
        assert stop_called.is_set()

    asyncio.run(exercise())


def test_crawler_emits_explicit_run_terminal_events() -> None:
    """Make normal completion and unhandled failure observable facts."""

    async def exercise(engine, expected_signal) -> None:
        """Drive one small Crawler with in-memory lifecycle collaborators."""
        emitted = []

        class SignalManager:
            """Capture terminal signals without starting a real dispatcher."""

            def start(self) -> None:
                """Represent dispatcher startup."""

            async def _safe_put(self, signal, data) -> None:
                """Capture one explicitly awaited lifecycle event."""
                emitted.append((signal, data))

        crawler = Crawler()
        crawler.signalManager = SignalManager()
        crawler.sessions = SimpleNamespace(start=lambda: None)
        crawler.engines = [engine]

        async def cleanup() -> None:
            """Represent one idempotent cleanup phase."""

        crawler._prepare_shutdown = cleanup
        crawler._close_runtime_state = cleanup

        if expected_signal is signals.run_failed:
            with pytest.raises(ValueError, match="broken engine"):
                await crawler.start_engines(None)
        else:
            await crawler.start_engines(None)

        assert emitted[-1][0] is expected_signal

    class CompletedEngine:
        """Complete normally for the terminal-event test."""

        async def start(self) -> None:
            """Return one successful Engine run."""

    class FailedEngine:
        """Raise an unhandled error for the terminal-event test."""

        async def start(self) -> None:
            """Raise one terminal Engine failure."""
            raise ValueError("broken engine")

    asyncio.run(exercise(CompletedEngine(), signals.run_completed))
    asyncio.run(exercise(FailedEngine(), signals.run_failed))
