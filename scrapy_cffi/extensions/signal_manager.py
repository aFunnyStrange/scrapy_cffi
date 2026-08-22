"""Dispatch optional observation signals with explicit async ownership."""

import asyncio
import inspect
from collections import defaultdict
from typing import Any, Awaitable, Callable, Optional, Set, TYPE_CHECKING, TypeVar, Union

if TYPE_CHECKING:
    from ..crawler import Crawler
    from ..extensions import SignalInfo
    from ..settings import SettingsInfo
    from ..repo.queue import KafkaQueueRepository

T = TypeVar("T")

class SignalManager:
    """Own signal buffering, callback tasks, and event-driven shutdown."""

    SignalCallback = Union[Callable[[T], Any], Callable[[T], Awaitable[Any]]]

    def __init__(
        self,
        stop_event: Optional[asyncio.Event] = None,
        settings: Optional["SettingsInfo"] = None,
        maxsize: int = 1000,
        kafka_repository: Optional["KafkaQueueRepository"] = None,
    ) -> None:
        """Initialize one bounded signal queue without starting its task."""
        self._listeners = defaultdict(list)
        self._queue = asyncio.Queue(maxsize=maxsize)
        self.stop_event = stop_event or asyncio.Event()
        self._run_task = None
        self._put_tasks: Set[asyncio.Task] = set()
        self._pending_tasks: Set[asyncio.Task] = set()
        from ..utils.log import init_logger
        log_info = settings.LOG_INFO if settings is not None else None
        self.logger = init_logger(log_info=log_info, logger_name=__name__)
        if kafka_repository:
            from ..utils.log import KafkaLoggingHandler
            kafka_handler = KafkaLoggingHandler(kafka=kafka_repository, stop_event=self.stop_event).create_fmt(settings)
            self.logger.addHandler(kafka_handler)

    @classmethod
    def from_crawler(cls, crawler: "Crawler") -> "SignalManager":
        """Construct a manager from crawler-owned runtime dependencies."""
        return cls(
            stop_event=crawler.stop_event, 
            settings=crawler.settings,
            kafka_repository=crawler.resources.kafka,
        )

    def connect(self, signal: object, callback: SignalCallback) -> None:
        """Subscribe a callable to one signal identity."""
        if not callable(callback):
            raise TypeError(f"Signal callback must be callable: got {type(callback)}")
        self._listeners[signal].append(callback)

    def send(self, signal: object, data: "SignalInfo") -> None:
        """Schedule a non-blocking enqueue while the runtime accepts events."""
        if self.stop_event.is_set() or (not self._listeners[signal]):
            return
        task = asyncio.create_task(self._safe_put(signal, data))
        self._put_tasks.add(task)
        task.add_done_callback(self._put_tasks.discard)

    async def _safe_put(self, signal: object, data: "SignalInfo") -> None:
        """Enqueue with bounded overload waiting and explicit drop logging."""
        if not self._listeners[signal]:
            return
        try:
            self._queue.put_nowait((signal, data))
        except asyncio.QueueFull:
            try:
                await asyncio.wait_for(self._queue.put((signal, data)), timeout=0.1)
            except asyncio.TimeoutError:
                if self.logger is not None:
                    self.logger.warning(
                        "[SignalManager] Signal queue full, dropped signal: %r",
                        signal,
                    )

    async def _run_callback(self, callback: SignalCallback, data: "SignalInfo") -> None:
        """Run one async callback while containing observation failures."""
        try:
            await callback(data)
        except asyncio.CancelledError:
            raise
        except Exception:
            if self.logger is not None:
                self.logger.exception("[SignalManager] Signal callback failed")

    async def _dispatch(self, signal: object, data: "SignalInfo") -> None:
        """Dispatch one queued signal to all current subscribers."""
        for callback in self._listeners[signal]:
            try:
                if inspect.iscoroutinefunction(callback):
                    task = asyncio.create_task(self._run_callback(callback, data))
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
                else:
                    callback(data)
            except Exception:
                if self.logger is not None:
                    self.logger.exception("[SignalManager] Signal callback failed")

    async def run(self) -> None:
        """Consume until the owner enqueues the explicit stop sentinel."""
        try:
            while True:
                signal, data = await self._queue.get()
                if signal is None:
                    return
                await self._dispatch(signal, data)
        except asyncio.CancelledError:
            if self.logger is not None:
                self.logger.warning(
                    "[SignalManager] run task cancelled; cancelling callbacks"
                )
            for task in self._pending_tasks:
                task.cancel()
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
            raise

    def start(self) -> None:
        """Start the single owned consumer task when it is not running."""
        if not self._run_task or self._run_task.done():
            self._run_task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        """Drain owned enqueues, consume the sentinel, and await callbacks."""
        if self._put_tasks:
            await asyncio.gather(*self._put_tasks, return_exceptions=True)

        if self._run_task:
            if not self._run_task.done():
                await self._queue.put((None, None))
            await self._run_task
            self._run_task = None

        if self._pending_tasks:
            if self.logger is not None:
                self.logger.info(
                    "[SignalManager] Waiting for %s pending callbacks",
                    len(self._pending_tasks),
                )
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
