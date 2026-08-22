"""Crawler lifecycle entrypoints (framework). Import lazily from scrapy_cffi root."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

from .crawler import Crawler

if TYPE_CHECKING:
    from .runtime import RunContext, RunOutcome
    from .settings import SettingsInfo


@dataclass
class SpiderRunConfig:
    """One Crawler + settings bundle; use with run_spiders for isolated configs on one loop."""

    settings: "SettingsInfo"
    start_type: int = 0  # 0 = scan SPIDERS_PATH dir, 1 = load SPIDERS_PATH as single class path
    run_context: Optional["RunContext"] = None


class CrawlerRunHandle:
    """Expose one crawler execution to an application-owned scheduler."""

    def __init__(
        self,
        crawler: Crawler,
        task: asyncio.Task,
        started_at: Optional[float] = None,
    ) -> None:
        """Retain execution ownership without creating a thread or process."""
        self.crawler = crawler
        self.task = task
        self.context = crawler.run_context
        self.started_at = started_at or time.time()
        self._outcome: Optional["RunOutcome"] = None
        self._wait_lock = asyncio.Lock()
        self._stop_requested = False

    @property
    def outcome(self) -> Optional["RunOutcome"]:
        """Return the terminal outcome after wait or stop has completed."""
        return self._outcome

    async def wait(self) -> "RunOutcome":
        """Wait for one execution and normalize its terminal runtime state."""
        from .runtime import RunOutcome, RunState

        async with self._wait_lock:
            if self._outcome is not None:
                return self._outcome
            state = RunState.COMPLETED
            error_type = None
            error_summary = None
            try:
                await asyncio.shield(self.task)
                if self._stop_requested:
                    state = RunState.CANCELLED
            except asyncio.CancelledError:
                if not self.task.cancelled():
                    raise
                state = RunState.CANCELLED
            except BaseException as exc:
                state = RunState.FAILED
                error_type = type(exc).__name__
                error_summary = str(exc)[:1000]
            self._outcome = RunOutcome(
                context=self.context,
                state=state,
                started_at=self.started_at,
                finished_at=time.time(),
                counters=self._collect_counters(),
                error_type=error_type,
                error_summary=error_summary,
            )
            return self._outcome

    async def stop(self) -> "RunOutcome":
        """Request graceful shutdown and return the normalized cancellation."""
        self._stop_requested = True
        await self.crawler.shutdown()
        if not self.task.done():
            self.task.cancel()
        return await self.wait()

    def _collect_counters(self) -> dict:
        """Collect available extension counters without requiring monitoring."""
        counters = {}
        for extension in self.crawler.extensions_list:
            extension_counters = getattr(extension, "counters", None)
            if isinstance(extension_counters, dict):
                counters.update(extension_counters)
        return counters


def cleanup_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel retained tasks and close a framework-created event loop."""
    pending = asyncio.all_tasks(loop=loop)
    for task in pending:
        task.cancel()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
    loop.close()


async def run_base(
    start_type: int,
    settings: "SettingsInfo",
    new_loop: bool = False,
    *args,
    run_context: Optional["RunContext"] = None,
    **kwargs,
) -> Tuple[Crawler, asyncio.Task]:
    """Initialize one Crawler and return its retained Engine task."""
    if new_loop:
        now_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(now_loop)
    else:
        now_loop = asyncio.get_running_loop()
    crawler = Crawler(run_context=run_context)
    robot_task = await crawler.do_initialization(settings=settings, start_type=start_type)
    engine_task = now_loop.create_task(crawler.start_engines(robot_task=robot_task, *args, **kwargs))
    return crawler, engine_task


def run_sync_base(
    start_type: int,
    settings: "SettingsInfo",
    new_loop: bool = True,
    *args,
    run_context: Optional["RunContext"] = None,
    **kwargs,
) -> None:
    """Own an event loop while running one Crawler to its terminal event."""
    if new_loop:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_running_loop()
    crawler: Optional[Crawler] = None

    async def main():
        """Run and close the single Crawler inside the selected event loop."""
        nonlocal crawler
        crawler = Crawler(run_context=run_context)
        robot_task = await crawler.do_initialization(settings=settings, start_type=start_type)
        try:
            await crawler.start_engines(robot_task, *args, **kwargs)
        finally:
            await crawler.shutdown()

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("KeyboardInterrupt detected, shutting down...")
        if crawler:
            loop.run_until_complete(crawler.shutdown())
    finally:
        cleanup_loop(loop=loop)


async def run_spider(settings: "SettingsInfo", new_loop: bool = False, *args, **kwargs):
    """Start one configured Spider and return its Crawler and task."""
    return await run_base(start_type=1, settings=settings, new_loop=new_loop, *args, **kwargs)


async def run_all_spiders(settings: "SettingsInfo", new_loop: bool = False, *args, **kwargs):
    """Start every Spider in the configured directory on one Crawler."""
    return await run_base(start_type=0, settings=settings, new_loop=new_loop, *args, **kwargs)


async def start_spider_run(
    settings: "SettingsInfo",
    *args,
    run_context: Optional["RunContext"] = None,
    **kwargs,
) -> CrawlerRunHandle:
    """Start one spider and return an outer-scheduler-friendly handle."""
    started_at = time.time()
    crawler, task = await run_spider(
        settings,
        False,
        *args,
        run_context=run_context,
        **kwargs,
    )
    return CrawlerRunHandle(crawler, task, started_at=started_at)


async def start_all_spiders_run(
    settings: "SettingsInfo",
    *args,
    run_context: Optional["RunContext"] = None,
    **kwargs,
) -> CrawlerRunHandle:
    """Start a configured spider directory and return one run handle."""
    started_at = time.time()
    crawler, task = await run_all_spiders(
        settings,
        False,
        *args,
        run_context=run_context,
        **kwargs,
    )
    return CrawlerRunHandle(crawler, task, started_at=started_at)


def run_spider_sync(settings: "SettingsInfo", new_loop: bool = True, *args, **kwargs):
    """Run one configured Spider through the synchronous compatibility API."""
    return run_sync_base(start_type=1, settings=settings, new_loop=new_loop, *args, **kwargs)


def run_all_spiders_sync(settings: "SettingsInfo", new_loop: bool = True, *args, **kwargs):
    """Run all configured Spiders through the synchronous compatibility API."""
    return run_sync_base(start_type=0, settings=settings, new_loop=new_loop, *args, **kwargs)


async def run_spiders(
    configs: Sequence[SpiderRunConfig],
    new_loop: bool = False,
    *args,
    **kwargs,
) -> Tuple[List[Crawler], List[asyncio.Task]]:
    """
    Start multiple Crawler instances on the same event loop.
    Each config carries its own SettingsInfo (managers, scheduler, concurrency).
    """
    if new_loop:
        now_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(now_loop)
    else:
        now_loop = asyncio.get_running_loop()

    crawlers: List[Crawler] = []
    tasks: List[asyncio.Task] = []
    for cfg in configs:
        crawler = Crawler(run_context=cfg.run_context)
        robot_task = await crawler.do_initialization(settings=cfg.settings, start_type=cfg.start_type)
        tasks.append(now_loop.create_task(crawler.start_engines(robot_task=robot_task, *args, **kwargs)))
        crawlers.append(crawler)
    return crawlers, tasks


def run_spiders_sync(
    configs: Sequence[SpiderRunConfig],
    new_loop: bool = True,
    *args,
    **kwargs,
) -> None:
    """Run multiple Crawler configs synchronously (each with its own SettingsInfo)."""
    if new_loop:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()

    crawlers: List[Crawler] = []

    async def main():
        """Run and close every configured Crawler on the selected loop."""
        nonlocal crawlers
        crawlers, tasks = await run_spiders(configs, new_loop=False, *args, **kwargs)
        try:
            await asyncio.gather(*tasks)
        finally:
            await asyncio.gather(
                *(crawler.shutdown() for crawler in crawlers),
                return_exceptions=False,
            )

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("KeyboardInterrupt detected, shutting down...")
        for crawler in crawlers:
            loop.run_until_complete(crawler.shutdown())
    finally:
        if new_loop:
            cleanup_loop(loop=loop)


__all__ = [
    "SpiderRunConfig",
    "CrawlerRunHandle",
    "Crawler",
    "cleanup_loop",
    "run_base",
    "run_sync_base",
    "run_spider",
    "run_all_spiders",
    "run_spider_sync",
    "run_all_spiders_sync",
    "run_spiders",
    "run_spiders_sync",
    "start_all_spiders_run",
    "start_spider_run",
]
