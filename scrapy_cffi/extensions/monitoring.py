"""Publish opt-in batched crawler observations to a monitoring Hub."""

import time
import asyncio
from typing import TYPE_CHECKING, Dict, Optional

from . import signals
from .base import Extension
from ..monitoring import MonitorClient, MonitorEvent
from ..runtime import EventCategory, RunContext, RunState, WorkerState

if TYPE_CHECKING:
    from ..config import MonitorInfo
    from ..hooks.signals import SignalsHooks
    from ..settings import SettingsInfo
    from .singal_info import SignalInfo


class CrawlerMonitorExtension(Extension):
    """Aggregate hot signals and publish lifecycle observations when enabled."""

    def __init__(self, hooks: "SignalsHooks", **kwargs) -> None:
        """Build one client without starting background tasks."""
        super().__init__(hooks, **kwargs)
        settings: "SettingsInfo" = kwargs.get("settings")
        if settings is None:
            settings = hooks.settings
        self.logger = kwargs.get("logger")
        if self.logger is None:
            self.logger = hooks.logger
        self.info: "MonitorInfo" = settings.MONITOR_INFO
        self.run_context = getattr(hooks, "run_context", None) or RunContext.create()
        self.worker_id = (
            self.info.WORKER_ID
            or self.run_context.worker_id
            or self.run_context.resolved_worker_id()
        )
        self.client = MonitorClient(self.info.HUB_URL, timeout=self.info.TIMEOUT)
        self._publish_lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._active_engines = 0
        self._sequence = 0
        self.counters: Dict[str, int] = {
            "request_scheduled": 0,
            "request_dropped": 0,
            "response_received": 0,
            "item_scraped": 0,
            "task_error": 0,
            "spider_error": 0,
        }
        self._batched_events = 0

    @classmethod
    def from_crawler(cls, hooks: "SignalsHooks", **kwargs):
        """Create the extension and register crawler observation callbacks."""
        extension = cls(hooks, **kwargs)
        hooks.signals.connect(signals.engine_started, extension.engine_started)
        hooks.signals.connect(signals.engine_stopped, extension.engine_stopped)
        hooks.signals.connect(signals.run_completed, extension.run_completed)
        hooks.signals.connect(signals.run_failed, extension.run_failed)
        hooks.signals.connect(signals.run_cancelled, extension.run_cancelled)
        hooks.signals.connect(signals.spider_opened, extension.spider_opened)
        hooks.signals.connect(signals.spider_closed, extension.spider_closed)
        hooks.signals.connect(signals.task_error, extension.task_error)
        hooks.signals.connect(signals.spider_error, extension.spider_error)
        hooks.signals.connect(signals.request_scheduled, extension.request_scheduled)
        hooks.signals.connect(signals.request_dropped, extension.request_dropped)
        hooks.signals.connect(signals.response_received, extension.response_received)
        hooks.signals.connect(signals.item_scraped, extension.item_scraped)
        return extension

    async def _publish(
        self,
        event: str,
        *,
        spider_name: Optional[str] = None,
        detail: Optional[str] = None,
        category: EventCategory = EventCategory.LIFECYCLE,
        worker_state: Optional[WorkerState] = None,
        run_state: Optional[RunState] = None,
    ) -> None:
        """Publish one bounded event while isolating Hub availability."""
        try:
            async with self._publish_lock:
                self._sequence += 1
                observation = MonitorEvent(
                    sequence=self._sequence,
                    worker_id=self.worker_id,
                    instance_id=self.run_context.instance_id,
                    run_id=self.run_context.run_id,
                    task_id=self.run_context.task_id,
                    event=event,
                    category=category,
                    timestamp=time.time(),
                    worker_state=worker_state,
                    run_state=run_state,
                    spider_name=spider_name,
                    counters=dict(self.counters),
                    detail=detail,
                )
                await self.client.publish(observation)
        except Exception as exc:
            self.logger.warning(
                "Crawler monitor Hub publish failed for %s: %r",
                event,
                exc,
            )

    async def _count_batched(self, event: str) -> None:
        """Count one hot event and publish only at the configured batch size."""
        self.counters[event] += 1
        self._batched_events += 1
        if self._batched_events >= self.info.EVENT_BATCH_SIZE:
            self._batched_events = 0
            await self._publish(
                "counters_updated",
                category=EventCategory.COUNTERS,
            )

    async def _heartbeat_loop(self) -> None:
        """Publish availability observations until explicitly cancelled."""
        try:
            while True:
                await asyncio.sleep(self.info.HEARTBEAT_INTERVAL)
                await self._publish(
                    "heartbeat",
                    category=EventCategory.HEARTBEAT,
                    worker_state=WorkerState.RUNNING,
                    run_state=RunState.RUNNING,
                )
        except asyncio.CancelledError:
            raise

    def _start_heartbeat(self) -> None:
        """Start the one extension-owned heartbeat task after first use."""
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_heartbeat(self) -> None:
        """Cancel and await the retained heartbeat task."""
        task = self._heartbeat_task
        self._heartbeat_task = None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def engine_started(self, data: "SignalInfo") -> None:
        """Register a running crawler engine with the Hub."""
        self._active_engines += 1
        await self._publish(
            "engine_started",
            worker_state=WorkerState.RUNNING,
            run_state=RunState.RUNNING,
        )
        self._start_heartbeat()

    async def engine_stopped(self, data: "SignalInfo") -> None:
        """Flush counters and mark one crawler engine stopped."""
        self._active_engines = max(0, self._active_engines - 1)
        if not self._active_engines:
            await self._stop_heartbeat()
        await self._publish(
            "engine_stopped",
            worker_state=(
                WorkerState.RUNNING
                if self._active_engines
                else WorkerState.STOPPED
            ),
            run_state=(
                RunState.RUNNING
                if self._active_engines
                else RunState.COMPLETED
            ),
        )

    async def run_completed(self, data: "SignalInfo") -> None:
        """Report explicit normal completion for the whole crawler run."""
        await self._stop_heartbeat()
        await self._publish(
            "run_completed",
            worker_state=WorkerState.STOPPED,
            run_state=RunState.COMPLETED,
        )

    async def run_failed(self, data: "SignalInfo") -> None:
        """Report an unhandled run failure without changing durable tasks."""
        await self._stop_heartbeat()
        detail = str(data.reason or data.exception)[:1000]
        await self._publish(
            "run_failed",
            detail=detail,
            category=EventCategory.ERROR,
            worker_state=WorkerState.STOPPED,
            run_state=RunState.FAILED,
        )

    async def run_cancelled(self, data: "SignalInfo") -> None:
        """Report explicit cancellation as distinct from a failed run."""
        await self._stop_heartbeat()
        await self._publish(
            "run_cancelled",
            detail=str(data.reason)[:1000],
            worker_state=WorkerState.STOPPED,
            run_state=RunState.CANCELLED,
        )

    async def spider_opened(self, data: "SignalInfo") -> None:
        """Register one opened spider name."""
        await self._publish(
            "spider_opened",
            spider_name=getattr(data.spider, "name", None),
        )

    async def spider_closed(self, data: "SignalInfo") -> None:
        """Record one closed spider name and the latest counters."""
        await self._publish(
            "spider_closed",
            spider_name=getattr(data.spider, "name", None),
        )

    async def task_error(self, data: "SignalInfo") -> None:
        """Record and immediately publish a task failure."""
        self.counters["task_error"] += 1
        await self._publish(
            "task_error",
            detail=str(data.reason)[:1000],
            category=EventCategory.ERROR,
        )

    async def spider_error(self, data: "SignalInfo") -> None:
        """Record and immediately publish a spider failure."""
        self.counters["spider_error"] += 1
        await self._publish(
            "spider_error",
            spider_name=getattr(data.spider, "name", None),
            detail=str(data.exception)[:1000],
            category=EventCategory.ERROR,
        )

    async def request_scheduled(self, data: "SignalInfo") -> None:
        """Aggregate a scheduled-request observation."""
        await self._count_batched("request_scheduled")

    async def request_dropped(self, data: "SignalInfo") -> None:
        """Aggregate a dropped-request observation."""
        await self._count_batched("request_dropped")

    async def response_received(self, data: "SignalInfo") -> None:
        """Aggregate a received-response observation."""
        await self._count_batched("response_received")

    async def item_scraped(self, data: "SignalInfo") -> None:
        """Aggregate a scraped-item observation."""
        await self._count_batched("item_scraped")

    async def close(self) -> None:
        """Stop the optional heartbeat without inventing a terminal state."""
        await self._stop_heartbeat()


__all__ = ["CrawlerMonitorExtension"]
