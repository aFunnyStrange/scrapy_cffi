"""Verify the crawler-owned lazy process-pool boundary."""

import asyncio
import os

from scrapy_cffi.crawler import Crawler
from scrapy_cffi.settings import SettingsInfo
from scrapy_cffi.utils.process import ProcessTaskManager


def _worker_identity(value: int) -> dict:
    """Return deterministic data and the worker PID from a picklable function."""
    return {"pid": os.getpid(), "value": value * 2}


def test_process_pool_starts_only_after_first_submission():
    """Avoid allocating an executor or child process for unused crawlers."""
    async def scenario():
        """Submit one task and close the manager after observing lazy start."""
        manager = ProcessTaskManager(max_workers=1)
        assert manager.started is False
        result = await manager.run(_worker_identity, value=21)
        assert manager.started is True
        assert result["value"] == 42
        assert result["pid"] != os.getpid()
        await manager.close()

    asyncio.run(scenario())


def test_crawler_constructs_process_manager_lazily_from_settings():
    """Create no manager until a spider explicitly requests process work."""
    crawler = Crawler()
    crawler.settings = SettingsInfo(PROCESS_POOL_MAX_WORKERS=3)
    assert crawler._process_task_manager is None
    manager = crawler.get_process_task_manager()
    assert manager.max_workers == 3
    assert manager.started is False


def test_media_process_settings_are_validated():
    """Keep process bounds positive and executable paths configurable."""
    settings = SettingsInfo(
        PROCESS_POOL_MAX_WORKERS=1,
        FFMPEG_MAX_PROCESSES=4,
        FFMPEG_EXECUTABLE="custom-ffmpeg",
        FFPROBE_EXECUTABLE="custom-ffprobe",
    )
    assert settings.PROCESS_POOL_MAX_WORKERS == 1
    assert settings.FFMPEG_MAX_PROCESSES == 4
    assert settings.FFMPEG_EXECUTABLE == "custom-ffmpeg"
    assert settings.FFPROBE_EXECUTABLE == "custom-ffprobe"
