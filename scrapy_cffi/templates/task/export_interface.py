import asyncio, sys, scrapy_cffi
from action_flow import *
from utils import *
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def do_func(init_data={}):
    Flow_obj = FunctionFlow(**init_data)
    result = await Flow_obj.action_flow()
    result["cookie_dict"] = Flow_obj.session.cookies.get_dict()
    return result

async def start_spider(settings, task_data):
    try:
        crawler, engine_task = await scrapy_cffi.run_spider(settings=settings, new_loop=False, task_data=task_data)
        await engine_task
        from scrapy_cffi.crawler import Crawler
        crawler: Crawler
        await crawler.shutdown()
    except asyncio.CancelledError:
        crawler.stop_event.set()
    except Exception as e:
        print(f"task_spider_result error: {e}")
    finally:
        return "爬虫执行完成"

async def do_collect(init_data={}):
    Flow_obj = CollectFlow(**init_data)
    result = await Flow_obj.create_collect_task_flow()
    if result.get("status"):
        task_data = result.get("data", {}).get("response_data", {})
        if not Flow_obj.redis:
            # If the crawler is not a continuously listening crawler, you can directly start
            from spiders.settings import create_settings
            settings = create_settings(spider_path="spiders.spiders.CustomSpider")

            # scheme 1
            import threading # You can also enable thread pooling and limit concurrency limits.
            threading.Thread(target=scrapy_cffi.run_spider_sync, kwargs=dict(settings=settings, task_data=task_data), daemon=True).start()

            # scheme 2
            asyncio.create_task(start_spider(settings=settings, task_data=task_data))
        print("main running")

    result["cookie_dict"] = Flow_obj.session.cookies.get_dict()
    return result

if __name__ == "__main__":
    """just debug the function here"""