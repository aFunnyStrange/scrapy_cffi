"""Publish opt-in batched crawler observations to a monitoring Hub."""

import os
import socket
import time
import asyncio
from typing import TYPE_CHECKING, Dict, Optional

from . import signals
from .base import Extension
from ..monitoring import MonitorClient, MonitorEvent

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
        self.worker_id = self.info.WORKER_ID or "%s:%s" % (
            socket.gethostname(),
            os.getpid(),
        )
        self.client = MonitorClient(self.info.HUB_URL, timeout=self.info.TIMEOUT)
        self._publish_lock = asyncio.Lock()
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
    ) -> None:
        """Publish one bounded event while isolating Hub availability."""
        observation = MonitorEvent(
            worker_id=self.worker_id,
            event=event,
            timestamp=time.time(),
            spider_name=spider_name,
            counters=dict(self.counters),
            detail=detail,
        )
        try:
            async with self._publish_lock:
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
            await self._publish("counters_updated")

    async def engine_started(self, data: "SignalInfo") -> None:
        """Register a running crawler engine with the Hub."""
        await self._publish("engine_started")

    async def engine_stopped(self, data: "SignalInfo") -> None:
        """Flush counters and mark one crawler engine stopped."""
        await self._publish("engine_stopped")

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
        await self._publish("task_error", detail=str(data.reason)[:1000])

    async def spider_error(self, data: "SignalInfo") -> None:
        """Record and immediately publish a spider failure."""
        self.counters["spider_error"] += 1
        await self._publish(
            "spider_error",
            spider_name=getattr(data.spider, "name", None),
            detail=str(data.exception)[:1000],
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


__all__ = ["CrawlerMonitorExtension"]
