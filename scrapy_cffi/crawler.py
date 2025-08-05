import json, asyncio, sys
from .core.api import *
from .interceptors import ChainManager, InterruptibleChainManager
# from .interceptors import DownloadInterceptor
from .interceptors.api import UpdateRequestSpiderInterceptor, RobotSpiderInterceptor
from .pipelines.api import _InnerPipeline
from .extensions import SignalManager
from .utils import load_object, get_class_name, get_all_spiders_cls, get_all_spiders_name, RobotsManager, get_run_py_dir
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .models.api import SettingsInfo
    from logging import Logger
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class Crawler:
    def __init__(self):
        self.run_py_dir = get_run_py_dir()
        self.stop_event = None
        self.global_lock = None

        self.settings: "SettingsInfo" = None
        self.scheduler = None
        self.taskManager: TaskManager = None
        self.downloader = None
        self.spiderInterceptor_chain = None
        self.downloadInterceptor_chain = None
        self.pipelines_chain = None
        self.sessions = None
        self.sessions_lock = None
        self.redisManager = None
        self.logger: "Logger" = None
        self.signalManager = None
        self.robot = None
        self.extensions_list = []

        self.spiders = None
        self.engines = None

    @staticmethod
    @asynccontextmanager
    async def empty_global_context():
        yield

    def init_output(self, class_list):
        return [get_class_name(it) for it in class_list] if isinstance(class_list, list) else [get_class_name(class_list)]

    async def do_initialization(self, settings: "SettingsInfo", start_type=0):
        self.stop_event = asyncio.Event()

        self.settings: "SettingsInfo" = settings
        if self.settings.MAX_GLOBAL_CONCURRENT_TASKS:
            global_sem = asyncio.BoundedSemaphore(self.settings.MAX_GLOBAL_CONCURRENT_TASKS)
            @asynccontextmanager
            async def global_sem_context():
                async with global_sem:
                    yield
            self.global_lock = global_sem_context
        else:
            self.global_lock = self.empty_global_context

        # if not logger: # To ensure log stability, it is no longer enabled
        from .utils import init_logger
        logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)
        self.logger = logger

        self.sessions_lock = asyncio.Lock()
        self.sessions = SessionManager.from_crawler(self)
        self.signalManager = SignalManager.from_crawler(self)
        self.robot = RobotsManager.from_crawler(self)
        
        # redis
        if self.settings.REDIS_INFO.resolved_url:
            from .databases import RedisManager
            self.redisManager = RedisManager.from_crawler(self)

        self.settings.SPIDER_INTERCEPTORS_PATH.value.extend([RobotSpiderInterceptor, UpdateRequestSpiderInterceptor])
        self.spiderInterceptor_chain = InterruptibleChainManager.from_crawler(self, class_list=self.settings.SPIDER_INTERCEPTORS_PATH.value)

        # self.settings.DOWNLOAD_INTERCEPTORS_PATH.value.insert(0, DownloadInterceptor)
        self.downloadInterceptor_chain = InterruptibleChainManager.from_crawler(self, class_list=self.settings.DOWNLOAD_INTERCEPTORS_PATH.value)

        self.settings.ITEM_PIPELINES_PATH.value.insert(0, _InnerPipeline)
        self.pipelines_chain = ChainManager.from_crawler(self, class_list=self.settings.ITEM_PIPELINES_PATH.value)

        from .hooks import signals_hooks
        for ext_cls in self.settings.EXTENSIONS_PATH.value:
            self.extensions_list.append(ext_cls.from_crawler(signals_hooks(self)))

        self.downloader = Downloader.from_crawler(self)

        # spider start type
        if not self.settings.SPIDERS_PATH:
            self.settings.SPIDERS_PATH = str(self.run_py_dir / "spiders")
            import warnings
            warnings.warn(f"not provided self.settings.SPIDERS_PATH，guessed to load -> {self.settings.SPIDERS_PATH}")
            start_type = 0
        if start_type:
            self.spiders = [load_object(path=self.settings.SPIDERS_PATH)]
            spiders_name = [spider.name for spider in self.spiders]
        else:
            self.spiders = get_all_spiders_cls(spiders_dir=self.settings.SPIDERS_PATH)
            spiders_name = get_all_spiders_name(logger=self.logger, spiders_cls_list=self.spiders)

        scheduler_path = self.settings.SCHEDULER
        if scheduler_path:
            scheduler_cls = load_object(path=scheduler_path)
        else:
            from .core.scheduler import Scheduler
            scheduler_cls = Scheduler
        self.scheduler = scheduler_cls.from_crawler(self, spiders_name)

        for spider_cls in self.spiders:
            has_redis_key = getattr(spider_cls, "redis_key", None)
            if has_redis_key:
                self.taskManager = TaskManager.from_crawler(self, is_distributed=True) # Shared by all spider engines; if any exist, start one to handle blocking
                break
        else:
            self.taskManager = TaskManager.from_crawler(self, is_distributed=False)

        robot_task = None
        if self.settings.ROBOTSTXT_OBEY:
            robot_urls = set()
            for spider_cls in self.spiders:
                scheme = getattr(spider_cls, "robot_scheme", "https").lower()
                for domain in getattr(spider_cls, "allowed_domains", []):
                    robot_urls.add(f"{scheme}://{domain}/robots.txt")
            now_loop = asyncio.get_running_loop()
            robot_task = now_loop.create_task(self.robot.load_rules_for_hosts(robot_urls))

        self.spiders = [spider.from_crawler(self) for spider in self.spiders]
        self.engines = [Engine.from_crawler(crawler=self, spider=spider) for spider in self.spiders]

        core_data = []
        for spider, engine in zip(self.spiders, self.engines):
            core_data.append({"spider": self.init_output(spider)[0], "engine": self.init_output(engine)[0]})
    
        init_data = {
            "taskManager": self.init_output(self.taskManager)[0],
            "sessions": self.init_output(self.sessions)[0],
            "scheduler": self.init_output(self.scheduler)[0],
            "downloader": self.init_output(self.downloader)[0],
            "spiderInterceptor_chain": self.init_output(self.settings.SPIDER_INTERCEPTORS_PATH.value),
            "downloadInterceptor_chain": self.init_output(self.settings.DOWNLOAD_INTERCEPTORS_PATH.value),
            "pipelines_chain": self.init_output(self.settings.ITEM_PIPELINES_PATH.value),
            "extensions": self.init_output(self.extensions_list),
            "core": core_data
        }
        init_text = json.dumps(init_data, indent=4, ensure_ascii=False)
        self.logger.debug(init_text)
        return robot_task
    
    async def start_engines(self, robot_task, *args, **kwargs):
        self.signalManager.start()
        self.sessions.start()
        if robot_task:
            await robot_task
        await asyncio.gather(*[engine.start(*args, **kwargs) for engine in self.engines])
        self.stop_event.set()
        await self.sessions.close_all()
        await self.signalManager.stop()

    async def shutdown(self):
        self.stop_event.set()
        self.taskManager.active_tasks = 0
        self.taskManager.tasks_done_event.set()
        self.taskManager.error_event.set()

        if not self.settings.SCHEDULER_PERSIST and self.redisManager:
            for spider in self.spiders:
                if getattr(spider, "redis_key", None):
                    await self.redisManager.delete(spider.redis_key)
            await self.redisManager.delete(self.settings.PROJECT_NAME)
            await self.redisManager.delete(self.settings._FILTER_NEW_SEEN_REQ_KEY)
            await self.redisManager.delete(self.settings._FILTER_IS_REQ_KEY)

        # await asyncio.sleep(1)
        for engine in self.engines:
            await engine.taskManager.cancel_all()
        await self.sessions.close_all()
        await self.signalManager.stop()

def cleanup_loop(loop: asyncio.AbstractEventLoop):
    pending = asyncio.all_tasks(loop=loop)
    for task in pending:
        task.cancel()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
    loop.close()

# One spider corresponds to one engine
# Run a single spider, where one set of components corresponds to one spider
async def run_spider(settings: "SettingsInfo", new_loop=False, *args, **kwargs):
    if new_loop: # Suitable for running in an independent thread or synchronous start, use with caution to avoid cross event loop operations
        now_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(now_loop)
    else: # Suitable for calling within an existing asynchronous environment (default)
        now_loop = asyncio.get_running_loop()
    crawler = Crawler()
    robot_task = await crawler.do_initialization(settings=settings, start_type=1)
    engine_task = now_loop.create_task(crawler.start_engines(robot_task=robot_task, *args, **kwargs))
    return crawler, engine_task

# Run all spiders, where one set of components corresponds to multiple spiders
async def run_all_spiders(settings: "SettingsInfo", new_loop=False, *args, **kwargs):
    if new_loop:
        now_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(now_loop)
    else:
        now_loop = asyncio.get_running_loop()
    crawler = Crawler()
    robot_task = await crawler.do_initialization(settings=settings, start_type=0)
    engine_task = now_loop.create_task(crawler.start_engines(robot_task=robot_task, *args, **kwargs))
    return crawler, engine_task

def run_spider_sync(settings: "SettingsInfo", new_loop=True, *args, **kwargs):
    if new_loop:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_running_loop()
    crawler: Crawler = None

    async def main():
        nonlocal crawler
        crawler = Crawler()
        robot_task = await crawler.do_initialization(settings=settings, start_type=1)
        await crawler.start_engines(robot_task, *args, **kwargs)
        crawler.stop_event.set()
        # await asyncio.Event().wait()
        await crawler.shutdown()

    if sys.platform != "win32":
        import signal
        def handler():
            print("Signal received, stopping...")
            loop.stop()

        try:
            loop.add_signal_handler(signal.SIGINT, handler)
            loop.add_signal_handler(signal.SIGTERM, handler)
        except NotImplementedError:
            pass

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("KeyboardInterrupt detected, shutting down...")
        if crawler:
            loop.run_until_complete(crawler.shutdown())
    finally:
        cleanup_loop(loop=loop)

def run_all_spiders_sync(settings: "SettingsInfo", new_loop=True, *args, **kwargs):
    if new_loop:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_running_loop()
    crawler: Crawler = None

    async def main():
        nonlocal crawler
        crawler = Crawler()
        robot_task = await crawler.do_initialization(settings=settings, start_type=0)
        await crawler.start_engines(robot_task, *args, **kwargs)
        crawler.stop_event.set()
        # await asyncio.Event().wait()
        await crawler.shutdown()

    if sys.platform != "win32":
        import signal
        def handler():
            loop.stop()
        try:
            loop.add_signal_handler(signal.SIGINT, handler)
            loop.add_signal_handler(signal.SIGTERM, handler)
        except NotImplementedError:
            pass

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("KeyboardInterrupt detected, shutting down...")
        if crawler:
            loop.run_until_complete(crawler.shutdown())
    finally:
        cleanup_loop(loop=loop)