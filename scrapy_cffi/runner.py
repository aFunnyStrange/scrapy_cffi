"""Crawler lifecycle entrypoints (framework). Import lazily from scrapy_cffi root."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Sequence, Tuple

from .crawler import Crawler

if TYPE_CHECKING:
    from .settings import SettingsInfo


@dataclass
class SpiderRunConfig:
    """One Crawler + settings bundle; use with run_spiders for isolated configs on one loop."""

    settings: "SettingsInfo"
    start_type: int = 0  # 0 = scan SPIDERS_PATH dir, 1 = load SPIDERS_PATH as single class path


def cleanup_loop(loop: asyncio.AbstractEventLoop) -> None:
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
    **kwargs,
) -> Tuple[Crawler, asyncio.Task]:
    if new_loop:
        now_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(now_loop)
    else:
        now_loop = asyncio.get_running_loop()
    crawler = Crawler()
    robot_task = await crawler.do_initialization(settings=settings, start_type=start_type)
    engine_task = now_loop.create_task(crawler.start_engines(robot_task=robot_task, *args, **kwargs))
    return crawler, engine_task


def run_sync_base(
    start_type: int,
    settings: "SettingsInfo",
    new_loop: bool = True,
    *args,
    **kwargs,
) -> None:
    if new_loop:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_running_loop()
    crawler: Crawler | None = None

    async def main():
        nonlocal crawler
        crawler = Crawler()
        robot_task = await crawler.do_initialization(settings=settings, start_type=start_type)
        await crawler.start_engines(robot_task, *args, **kwargs)
        crawler.stop_event.set()
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
    return await run_base(start_type=1, settings=settings, new_loop=new_loop, *args, **kwargs)


async def run_all_spiders(settings: "SettingsInfo", new_loop: bool = False, *args, **kwargs):
    return await run_base(start_type=0, settings=settings, new_loop=new_loop, *args, **kwargs)


def run_spider_sync(settings: "SettingsInfo", new_loop: bool = True, *args, **kwargs):
    return run_sync_base(start_type=1, settings=settings, new_loop=new_loop, *args, **kwargs)


def run_all_spiders_sync(settings: "SettingsInfo", new_loop: bool = True, *args, **kwargs):
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
        crawler = Crawler()
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
        nonlocal crawlers
        crawlers, tasks = await run_spiders(configs, new_loop=False, *args, **kwargs)
        await asyncio.gather(*tasks)
        for crawler in crawlers:
            crawler.stop_event.set()
        for crawler in crawlers:
            await crawler.shutdown()

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
]
