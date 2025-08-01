# runner.py
import asyncio
import sys
import scrapy_cffi
from settings import create_settings
from typing import Tuple
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from scrapy_cffi.utils import setup_uvloop_once
setup_uvloop_once()

# 普通用户
def main(*args, **kwargs):
    settings = create_settings(spider_path="spiders.CustomSpider")

    # 兼容 scrapy settings.py
    # from scrapy_cffi import load_settings_with_path
    # settings = load_settings_with_path()

    scrapy_cffi.run_spider_sync(settings=settings, *args, **kwargs)

def main_all(*args, **kwargs):
    from scrapy_cffi.utils import get_run_py_dir
    spider_path = str(get_run_py_dir() / "spiders") # must be a directory when mode is 'run_all_spiders', since all spider files will be loaded from it
    settings = create_settings(spider_path=spider_path)

    # 兼容 scrapy settings.py
    # from scrapy_cffi import load_settings_with_path
    # settings = load_settings_with_path()
    
    scrapy_cffi.run_all_spiders_sync(settings=settings, *args, **kwargs)

# 高级用户
async def advance_main(*args, **kwargs) -> Tuple[scrapy_cffi.crawler.Crawler, asyncio.Task]:
    settings = create_settings(spider_path="spiders.CustomSpider")

    # 兼容 scrapy settings.py
    # from scrapy_cffi import load_settings_with_path
    # settings = load_settings_with_path()

    crawler, engine_task = await scrapy_cffi.run_spider(settings=settings, new_loop=False, *args, **kwargs)
    return crawler, engine_task

async def advance_main_all(*args, **kwargs) -> Tuple[scrapy_cffi.crawler.Crawler, asyncio.Task]:
    from scrapy_cffi.utils import get_run_py_dir
    spider_path = str(get_run_py_dir() / "spiders") # must be a directory when mode is 'run_all_spiders', since all spider files will be loaded from it
    settings = create_settings(spider_path=spider_path)

    # 兼容 scrapy settings.py
    # from scrapy_cffi import load_settings_with_path
    # settings = load_settings_with_path()

    crawler, engine_task = await scrapy_cffi.run_all_spiders(settings=settings, new_loop=False, *args, **kwargs)
    return crawler, engine_task

if __name__ == "__main__":
    # 高级用户，自行持有 loop，自行管理 task
    def setup_signal_handlers(shutdown_event: asyncio.Event):
        if sys.platform != "win32":
            import signal

            def _handle_signal():
                print(">>> [signal] Received stop signal")
                shutdown_event.set()

            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, _handle_signal)
                except NotImplementedError:
                    pass

        else:
            print(">>> [info] Signal handlers not supported on Windows, fallback to KeyboardInterrupt.")

    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()
    global crawler
    crawler: scrapy_cffi.crawler.Crawler = None

    setup_signal_handlers(shutdown_event)

    async def demo_main():
        global crawler
        # crawler, engine_task = await advance_main()
        crawler, engine_task = await advance_main_all()

        done, _ = await asyncio.wait(
            [engine_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED
        )

        if shutdown_event.is_set():
            print(">>> [main] Triggered shutdown, cleaning up...")
        else:
            print(">>> [main] Task finished normally.")

        await crawler.shutdown()

    try:
        loop.run_until_complete(demo_main())
    except KeyboardInterrupt:
        print(">>> [KeyboardInterrupt] fallback triggered")
        if crawler:
            loop.run_until_complete(crawler.shutdown())
    finally:
        scrapy_cffi.cleanup_loop(loop=loop)


    # ————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————
    # 普通用户（内部自动 new loop）
    import threading
    t = threading.Thread(target=main)
    t.start()
    t.join()
    t = threading.Thread(target=main_all)
    t.start()
    t.join()