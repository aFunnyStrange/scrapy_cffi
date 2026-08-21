"""Verify finite crawler producers and session references terminate cleanly."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from scrapy_cffi.core.engine import Engine
from scrapy_cffi.core.downloader.internet import HttpRequest
from scrapy_cffi.core.sessions import CloseSignal, SessionManager
from scrapy_cffi.core.tasks import TaskManager
from scrapy_cffi.interceptors import ChainNextEnum, ChainResult
from scrapy_cffi.settings import SettingsInfo
from scrapy_cffi.utils.concurrency import CallFunction


class _SignalManager:
    """Provide the synchronous and asynchronous signal methods used by Engine."""

    def send(self, **kwargs) -> None:
        """Accept a non-blocking signal."""

    async def _safe_put(self, **kwargs) -> None:
        """Accept a final ordered signal."""


class _EventDrivenDistributedScheduler:
    """Block for transport input without treating emptiness as completion."""

    is_distributed = True

    def __init__(self) -> None:
        """Create a scheduler that can only be stopped by task cancellation."""
        self.waiting = asyncio.Event()

    async def get(self, spider):
        """Wait for a real broker event instead of returning an empty marker."""
        self.waiting.set()
        await asyncio.Event().wait()


class _FiniteIngressSpider:
    """Model a producer whose configured input quota is already complete."""

    name = "finite-ingress"

    async def start(self):
        """Complete explicitly without manufacturing an empty-queue signal."""
        if False:
            yield None


class _ContinuousIngressSpider:
    """Model a producer that remains subscribed until external shutdown."""

    name = "continuous-ingress"

    def __init__(self) -> None:
        """Expose the real subscription state as an event."""
        self.listening = asyncio.Event()

    async def start(self):
        """Wait indefinitely for a real ingress or stop event."""
        self.listening.set()
        await asyncio.Event().wait()
        if False:
            yield None


@asynccontextmanager
async def _global_lock():
    """Provide TaskManager's configured concurrency context."""
    yield


class _Cp1252Logger:
    """Reject task log messages that a default Windows console cannot encode."""

    def __init__(self) -> None:
        """Collect messages after validating the Windows-compatible encoding."""
        self.messages = []

    def debug(self, message: str) -> None:
        """Model the cp1252 stream used by a GitHub-hosted Windows runner."""
        message.encode("cp1252")
        self.messages.append(message)


def test_task_manager_debug_logs_are_windows_console_safe() -> None:
    """Task lifecycle logging must not manufacture a Windows traceback."""

    async def run() -> None:
        """Execute one managed task through its add/end debug messages."""
        manager = TaskManager(
            stop_event=asyncio.Event(),
            global_lock=_global_lock,
            signalManager=_SignalManager(),
            settings=SettingsInfo(),
        )
        logger = _Cp1252Logger()
        manager.logger = logger

        async def noop() -> None:
            """Complete normally so both lifecycle messages are emitted."""

        task = await manager.create(CallFunction(noop))
        await task

        assert len(logger.messages) == 2
        assert all(":" in message for message in logger.messages)

    asyncio.run(run())


def test_integration_finite_distributed_engine_cancels_its_ingress_producer() -> None:
    """Finish from producer completion without polling an empty scheduler."""

    async def run() -> None:
        """Run the real Engine and TaskManager ownership boundary."""
        stop_event = asyncio.Event()
        settings = SettingsInfo(
            ROBOTSTXT_OBEY=False,
            MAX_SCHEDULER_LOOP_NUM=1,
        )
        signals = _SignalManager()
        task_manager = TaskManager(
            stop_event=stop_event,
            global_lock=_global_lock,
            signalManager=signals,
            settings=settings,
            is_distributed=True,
        )
        spider = _FiniteIngressSpider()
        scheduler = _EventDrivenDistributedScheduler()
        engine = Engine.__new__(Engine)
        engine.stop_event = stop_event
        engine.taskManager = task_manager
        engine.settings = settings
        engine.signalManager = signals
        engine.scheduler = scheduler
        engine.spider = spider
        engine.pipelines_chain = SimpleNamespace(chain_list=[])
        engine.max_inflight_downloader_tasks = 50
        engine.scheduler_loop = engine._distributed_scheduler_loop

        await asyncio.wait_for(engine.start(), timeout=2)

        assert scheduler.waiting.is_set()
        assert not task_manager.error_event.is_set()
        assert task_manager.active_object_tasks.get(id(engine), 0) == 0

    asyncio.run(run())


def test_integration_continuous_engine_keeps_listening_without_stop_event() -> None:
    """A continuous producer must not exit merely because no work has arrived."""

    async def run() -> None:
        """Observe subscription state, then cancel through the owner."""
        stop_event = asyncio.Event()
        settings = SettingsInfo(
            ROBOTSTXT_OBEY=False,
            MAX_SCHEDULER_LOOP_NUM=1,
        )
        signals = _SignalManager()
        task_manager = TaskManager(
            stop_event=stop_event,
            global_lock=_global_lock,
            signalManager=signals,
            settings=settings,
            is_distributed=True,
        )
        spider = _ContinuousIngressSpider()
        scheduler = _EventDrivenDistributedScheduler()
        engine = Engine.__new__(Engine)
        engine.stop_event = stop_event
        engine.taskManager = task_manager
        engine.settings = settings
        engine.signalManager = signals
        engine.scheduler = scheduler
        engine.spider = spider
        engine.pipelines_chain = SimpleNamespace(chain_list=[])
        engine.max_inflight_downloader_tasks = 50
        engine.scheduler_loop = engine._distributed_scheduler_loop

        engine_task = asyncio.create_task(engine.start())
        await spider.listening.wait()
        await scheduler.waiting.wait()

        assert not engine_task.done()
        assert not task_manager.error_event.is_set()

        engine_task.cancel()
        await asyncio.gather(engine_task, return_exceptions=True)
        assert not task_manager.error_event.is_set()

    asyncio.run(run())


def test_run_all_keeps_listening_after_its_finite_engine_finishes() -> None:
    """One finite Engine cannot terminate a mixed run-all Crawler."""

    async def run() -> None:
        """Drive both Engine completion events through Crawler.start_engines."""
        from scrapy_cffi.crawler import Crawler

        finite_finished = asyncio.Event()
        continuous_listening = asyncio.Event()
        continuous_finished = asyncio.Event()
        shutdown_prepared = asyncio.Event()
        runtime_closed = asyncio.Event()

        class FiniteEngine:
            """Represent an Engine whose producer and owned work are complete."""

            async def start(self) -> None:
                """Publish real finite completion and return."""
                finite_finished.set()

        class ContinuousEngine:
            """Represent an Engine retaining a live ingress subscription."""

            async def start(self) -> None:
                """Remain active until its explicit completion event arrives."""
                continuous_listening.set()
                await continuous_finished.wait()

        crawler = Crawler()
        crawler.signalManager = SimpleNamespace(start=lambda: None)
        crawler.sessions = SimpleNamespace(start=lambda: None)
        crawler.engines = [FiniteEngine(), ContinuousEngine()]

        async def prepare_shutdown() -> None:
            """Record the shared shutdown boundary."""
            shutdown_prepared.set()

        async def close_runtime_state() -> None:
            """Record final runtime closure."""
            runtime_closed.set()

        crawler._prepare_shutdown = prepare_shutdown
        crawler._close_runtime_state = close_runtime_state

        run_all_task = asyncio.create_task(crawler.start_engines(robot_task=None))
        await finite_finished.wait()
        await continuous_listening.wait()

        assert not run_all_task.done()
        assert not shutdown_prepared.is_set()

        continuous_finished.set()
        await asyncio.wait_for(run_all_task, timeout=1)

        assert shutdown_prepared.is_set()
        assert runtime_closed.is_set()

    asyncio.run(run())


def test_unit_explicit_completion_waits_for_owned_request_event() -> None:
    """Producer completion alone cannot close an Engine with owned work."""

    async def run() -> None:
        """Release one request and observe the completion event immediately."""
        stop_event = asyncio.Event()
        settings = SettingsInfo(ROBOTSTXT_OBEY=False)
        signals = _SignalManager()
        task_manager = TaskManager(
            stop_event=stop_event,
            global_lock=_global_lock,
            signalManager=signals,
            settings=settings,
        )
        engine = Engine.__new__(Engine)
        engine.taskManager = task_manager
        engine.signalManager = signals
        request = HttpRequest(url="https://example.test")
        engine._track_request(request)
        producer_task = asyncio.create_task(asyncio.sleep(0))
        completion_task = asyncio.create_task(
            engine._wait_for_explicit_completion(producer_task)
        )
        await producer_task
        await asyncio.sleep(0)

        assert not completion_task.done()

        engine._release_request(request)
        await asyncio.wait_for(completion_task, timeout=1)

    asyncio.run(run())


def test_unit_session_end_signal_balances_its_acquired_reference() -> None:
    """Release the CloseSignal reference only after marking the session ended."""

    async def run() -> None:
        """Pass a session-end result through the real Engine branch."""
        sessions = SessionManager(
            asyncio.Event(),
            SettingsInfo(ROBOTSTXT_OBEY=False),
        )
        session_id = "finite-session"
        sessions.acquire(session_id)
        engine = Engine.__new__(Engine)
        engine.sessions = sessions

        await engine.manager_spiderinterceptors_result(
            ChainResult(
                next=ChainNextEnum.SESSION,
                signal=CloseSignal(session_id=session_id, session_end=True),
            )
        )

        assert sessions._ref_counts[session_id] == 0
        assert session_id in sessions._pending_close_set
        await sessions.close_all()

    asyncio.run(run())
