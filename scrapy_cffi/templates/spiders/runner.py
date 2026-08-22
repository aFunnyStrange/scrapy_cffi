# runner.py
import asyncio
import sys
from settings import create_settings
from typing import Optional, Tuple, Type

from scrapy_cffi.crawler import Crawler
from scrapy_cffi.runtime import RunContext
from scrapy_cffi.runner import (
    CrawlerRunHandle,
    cleanup_loop,
    run_all_spiders,
    run_all_spiders_sync,
    run_spider,
    run_spider_sync,
    start_spider_run,
)
from scrapy_cffi.spiders import BaseSpider

# <scrapy-cffi:default-spider>
DEFAULT_SPIDER: Optional[Type[BaseSpider]] = None
# </scrapy-cffi:default-spider>
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from scrapy_cffi.utils.common import get_or_create_loop, setup_uvloop_once
setup_uvloop_once()

# Ordinary users
def main(
    spider_cls: Optional[Type[BaseSpider]] = DEFAULT_SPIDER,
    *args,
    **kwargs,
):
    if spider_cls is None:
        raise RuntimeError(
            "No default spider is configured. Run `scrapy-cffi genspider ...` "
            "or pass a Spider class to main(spider_cls=...)."
        )
    settings = create_settings(spider_path=spider_cls)

    # compatible scrapy settings.py
    # from scrapy_cffi import load_settings_with_path
    # settings = load_settings_with_path()

    run_spider_sync(settings=settings, *args, **kwargs)

def main_all(*args, **kwargs):
    from scrapy_cffi.utils.common import get_run_py_dir
    spider_path = str(get_run_py_dir() / "spiders") # must be a directory when mode is 'run_all_spiders', since all spider files will be loaded from it
    settings = create_settings(spider_path=spider_path)

    # compatible scrapy settings.py
    # from scrapy_cffi import load_settings_with_path
    # settings = load_settings_with_path()
    
    run_all_spiders_sync(settings=settings, *args, **kwargs)

# Advanced Users
async def advance_main(
    spider_cls: Optional[Type[BaseSpider]] = DEFAULT_SPIDER,
    *args,
    **kwargs,
) -> Tuple[Crawler, asyncio.Task]:
    if spider_cls is None:
        raise RuntimeError(
            "No default spider is configured. Run `scrapy-cffi genspider ...` "
            "or pass a Spider class to advance_main(spider_cls=...)."
        )
    settings = create_settings(spider_path=spider_cls)

    # compatible scrapy settings.py
    # from scrapy_cffi import load_settings_with_path
    # settings = load_settings_with_path()

    crawler, engine_task = await run_spider(settings=settings, new_loop=False, *args, **kwargs)
    return crawler, engine_task

async def advance_main_all(*args, **kwargs) -> Tuple[Crawler, asyncio.Task]:
    from scrapy_cffi.utils.common import get_run_py_dir
    spider_path = str(get_run_py_dir() / "spiders") # must be a directory when mode is 'run_all_spiders', since all spider files will be loaded from it
    settings = create_settings(spider_path=spider_path)

    # compatible scrapy settings.py
    # from scrapy_cffi import load_settings_with_path
    # settings = load_settings_with_path()

    crawler, engine_task = await run_all_spiders(settings=settings, new_loop=False, *args, **kwargs)
    return crawler, engine_task

async def managed_main(
    task_id: str,
    spider_cls: Optional[Type[BaseSpider]] = DEFAULT_SPIDER,
    *args,
    **kwargs,
) -> CrawlerRunHandle:
    """Expose one correlated run for Celery or an application manager."""
    if spider_cls is None:
        raise RuntimeError("No default spider is configured.")
    settings = create_settings(spider_path=spider_cls)
    context = RunContext.create(task_id=task_id)
    return await start_spider_run(
        settings,
        *args,
        run_context=context,
        **kwargs,
    )

# ————————————————————————————————————————————————————————————————————————
def setup_signal_handlers(loop: asyncio.AbstractEventLoop, shutdown_event: asyncio.Event):
    import signal

    def _handle_signal(*_):
        print(">>> [signal] Received stop signal")
        loop.call_soon_threadsafe(shutdown_event.set)

    if sys.platform == "win32":
        for sig in (signal.SIGINT, signal.SIGBREAK):
            signal.signal(sig, _handle_signal)
        return

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except (NotImplementedError, ValueError):
            pass

if __name__ == "__main__":
    loop = get_or_create_loop()
    shutdown_event = asyncio.Event()
    setup_signal_handlers(loop, shutdown_event)

    crawler: Optional[Crawler] = None

    async def demo_main():
        global crawler
        # crawler, engine_task = await advance_main()
        crawler, engine_task = await advance_main_all()

        shutdown_task = asyncio.create_task(shutdown_event.wait())
        done, _ = await asyncio.wait(
            [engine_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        if shutdown_event.is_set():
            print(">>> [main] Triggered shutdown, cleaning up...")
        else:
            print(">>> [main] Task finished normally.")

        await crawler.shutdown()
        if shutdown_task is not engine_task and not shutdown_task.done():
            shutdown_task.cancel()
        await asyncio.gather(shutdown_task, engine_task, return_exceptions=True)

    try:
        loop.run_until_complete(demo_main())
    except KeyboardInterrupt:
        print(">>> [KeyboardInterrupt] manual stop")
        if crawler:
            loop.run_until_complete(crawler.shutdown())
    finally:
        cleanup_loop(loop=loop)

    # To use the synchronous helpers instead: uncomment in your own copy.
    # import threading
    # threading.Thread(target=main).start()
