import json, asyncio, sys
from functools import partial
from pathlib import Path
from .core.api import *
from .interceptors import ChainManager, InterruptibleChainManager
# from .interceptors import DownloadInterceptor
from .interceptors.api import (
    ClientHintsDownloadInterceptor,
    RobotSpiderInterceptor,
    UpdateRequestSpiderInterceptor,
)
from .pipelines import Pipeline
from .extensions import SignalManager
from .utils.common import (
    load_object,
    get_class_name,
    get_all_spiders_cls,
    get_all_spiders_name,
    get_run_py_dir,
    async_context_factory,
)
from .utils.robot import RobotsManager
from .settings import merge_spider_settings
from typing import TYPE_CHECKING, Dict
if TYPE_CHECKING:
    from .settings import SettingsInfo
    from logging import Logger
    from .service import ResourceService

class Crawler:
    def __init__(self):
        self.run_py_dir = get_run_py_dir()
        self.stop_event = None
        self.global_lock = None

        self.settings: "SettingsInfo" = None
        self.schedulers: Dict[str, object] = {}
        self.taskManager: TaskManager = None
        self.downloader = None
        self.spiderInterceptor_chain = None
        self.downloadInterceptor_chain = None
        self.pipelines_chain = None
        self.sessions = None
        self.http_session_factory = None
        self._process_task_manager = None
        self.sessions_lock = None

        self.resources: "ResourceService" = None

        self.logger: "Logger" = None
        self.signalManager = None
        self.robot = None
        self.extensions_list = []

        self.spiders = None
        self.engines = None
        self._shutdown_lock = None
        self._runtime_close_lock = None
        self._shutdown_prepared = False
        self._runtime_closed = False

    @property
    def scheduler(self):
        """When exactly one spider is loaded, exposes its scheduler for legacy code paths."""
        if len(self.schedulers) == 1:
            return next(iter(self.schedulers.values()))
        return None

    def init_output(self, class_list):
        return [get_class_name(it) for it in class_list] if isinstance(class_list, list) else [get_class_name(class_list)]

    def _build_resources(self) -> "ResourceService":
        """Assemble concrete clients, repositories, and shared retry policy."""
        from .composition import build_resource_service

        return build_resource_service(self.settings, self.stop_event, logger=self.logger)

    def get_process_task_manager(self):
        """Return the crawler-owned lazy pool without starting worker processes."""
        if self._process_task_manager is None:
            from .utils.process import ProcessTaskManager

            self._process_task_manager = ProcessTaskManager(
                max_workers=self.settings.PROCESS_POOL_MAX_WORKERS,
            )
        return self._process_task_manager

    async def do_initialization(self, settings: "SettingsInfo", start_type=0):
        self.stop_event = asyncio.Event()
        self._shutdown_lock = asyncio.Lock()
        self._runtime_close_lock = asyncio.Lock()
        self._shutdown_prepared = False
        self._runtime_closed = False

        self.settings: "SettingsInfo" = settings
        from .composition import activate_http_runtime

        activate_http_runtime(self.settings)
        if self.settings.CPY_EXTENSIONS.RESOURCES:
            from .cpy import CExtensionLoader

            CExtensionLoader(resource_dir=self.settings.CPY_EXTENSIONS.DIR).load_all(
                configs=self.settings.CPY_EXTENSIONS.RESOURCES
            )

        self.global_lock = async_context_factory(
            max_tasks=self.settings.MAX_GLOBAL_CONCURRENT_TASKS,
            semaphore_cls=asyncio.BoundedSemaphore
        )

        # if not logger: # To ensure log stability, it is no longer enabled
        from .utils.log import init_logger, KafkaLoggingHandler
        logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)
        self.logger = logger
        self.resources = self._build_resources()
        await self.resources.start()
        if self.resources.kafka:
            kafka_handler = KafkaLoggingHandler(kafka=self.resources.kafka, stop_event=self.stop_event).create_fmt(self.settings)
            self.logger.addHandler(kafka_handler)

        self.sessions_lock = asyncio.Lock()
        session_factory = self.settings.HTTP_SESSION_FACTORY
        if isinstance(session_factory, str):
            session_factory = load_object(session_factory)
        if session_factory is None:
            from .platform.curl_cffi import CurlCffiHttpSession

            session_factory = partial(
                CurlCffiHttpSession,
            )
        if not callable(session_factory):
            raise TypeError("HTTP_SESSION_FACTORY must be callable or an import path")
        self.http_session_factory = session_factory
        self.sessions = SessionManager.from_crawler(self)
        self.signalManager = SignalManager.from_crawler(self)
        self.robot = RobotsManager.from_crawler(self)
        
        self.settings.SPIDER_INTERCEPTORS_PATH.value.extend([RobotSpiderInterceptor, UpdateRequestSpiderInterceptor])
        self.spiderInterceptor_chain = InterruptibleChainManager.from_crawler(self, class_list=self.settings.SPIDER_INTERCEPTORS_PATH.value)

        if (
            ClientHintsDownloadInterceptor
            not in self.settings.DOWNLOAD_INTERCEPTORS_PATH.value
        ):
            self.settings.DOWNLOAD_INTERCEPTORS_PATH.value.append(
                ClientHintsDownloadInterceptor
            )
        self.downloadInterceptor_chain = InterruptibleChainManager.from_crawler(self, class_list=self.settings.DOWNLOAD_INTERCEPTORS_PATH.value)

        self.settings.ITEM_PIPELINES_PATH.value.insert(0, Pipeline)
        self.pipelines_chain = ChainManager.from_crawler(self, class_list=self.settings.ITEM_PIPELINES_PATH.value)

        from .hooks import signals_hooks
        for ext_cls in self.settings.EXTENSIONS_PATH.value:
            self.extensions_list.append(ext_cls.from_crawler(
                hooks=signals_hooks(self), 
                resources=self.resources,
        ))

        self.downloader = Downloader.from_crawler(self)

        # spider start type
        if not self.settings.SPIDERS_PATH:
            self.settings.SPIDERS_PATH = str(self.run_py_dir / "spiders")
            self.logger.warning(f"not provided self.settings.SPIDERS_PATH, guessed to load -> {self.settings.SPIDERS_PATH}")
            start_type = 0
        if start_type:
            spider_target = self.settings.SPIDERS_PATH
            spider_cls = (
                load_object(path=spider_target)
                if isinstance(spider_target, str)
                else spider_target
            )
            if not isinstance(spider_cls, type):
                raise TypeError(
                    "SPIDERS_PATH must be a spider class or import path in single-spider mode"
                )
            self.spiders = [spider_cls]
        else:
            if not isinstance(self.settings.SPIDERS_PATH, (str, Path)):
                raise TypeError(
                    "SPIDERS_PATH must be a directory path in run-all-spiders mode"
                )
            self.spiders = get_all_spiders_cls(spiders_dir=self.settings.SPIDERS_PATH)
            get_all_spiders_name(logger=self.logger, spiders_cls_list=self.spiders)

        spider_cls_list = self.spiders

        scheduler_path = self.settings.SCHEDULER
        configured_scheduler_cls = None
        if scheduler_path:
            configured_scheduler_cls = (
                load_object(path=scheduler_path)
                if isinstance(scheduler_path, str)
                else scheduler_path
            )
            if not isinstance(configured_scheduler_cls, type):
                raise TypeError("SCHEDULER must be a scheduler class or import path")

        self.schedulers.clear()
        for spider_cls in spider_cls_list:
            scheduler_cls = configured_scheduler_cls
            if scheduler_cls is None:
                from .core.scheduler import Scheduler
                from .spiders.kafka import KafkaSpider
                from .spiders.rabbitmq import RabbitmqSpider
                from .spiders.redis import RedisSpider
                if issubclass(spider_cls, KafkaSpider):
                    from .core.scheduler.kafka import KafkaScheduler
                    scheduler_cls = KafkaScheduler
                elif issubclass(spider_cls, RabbitmqSpider):
                    from .core.scheduler.rabbitmq import RabbitMqScheduler
                    scheduler_cls = RabbitMqScheduler
                elif issubclass(spider_cls, RedisSpider):
                    from .core.scheduler.redis import RedisScheduler
                    scheduler_cls = RedisScheduler
                else:
                    scheduler_cls = Scheduler
            name = spider_cls.name
            spider_settings = merge_spider_settings(self.settings, spider_cls)
            self.schedulers[name] = scheduler_cls.from_crawler(
                self,
                spiders_name=[name],
                spider_classes=[spider_cls],
                settings=spider_settings,
            )

        is_distributed = any(
            scheduler.is_distributed for scheduler in self.schedulers.values()
        )
        self.taskManager = TaskManager.from_crawler(self, is_distributed=is_distributed)

        robot_task = None
        if self.settings.ROBOTSTXT_OBEY:
            robot_urls = set()
            for spider_cls in spider_cls_list:
                scheme = getattr(spider_cls, "robot_scheme", "https").lower()
                for domain in getattr(spider_cls, "allowed_domains", []):
                    from .utils.domain import robots_txt_url

                    robot_urls.add(robots_txt_url(scheme, domain))
            now_loop = asyncio.get_running_loop()
            robot_task = now_loop.create_task(self.robot.load_rules_for_hosts(robot_urls))

        self.spiders = [
            spider_cls.from_crawler(self, scheduler=self.schedulers[spider_cls.name])
            for spider_cls in spider_cls_list
        ]
        self.engines = [
            Engine.from_crawler(crawler=self, spider=spider, scheduler=self.schedulers[spider.name])
            for spider in self.spiders
        ]

        core_data = []
        for spider, engine in zip(self.spiders, self.engines):
            core_data.append({"spider": self.init_output(spider)[0], "engine": self.init_output(engine)[0]})
    
        init_data = {
            "taskManager": self.init_output(self.taskManager)[0],
            "sessions": self.init_output(self.sessions)[0],
            "schedulers": {n: self.init_output(s)[0] for n, s in self.schedulers.items()},
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
        # All spiders share this thread's asyncio loop; engines run concurrently via gather.
        await asyncio.gather(*[engine.start(*args, **kwargs) for engine in self.engines])
        await self._prepare_shutdown()
        await self._close_runtime_state()

    async def _prepare_shutdown(self):
        """Run the broker-writable shutdown phase exactly once."""
        if self._shutdown_lock is None:
            self._shutdown_lock = asyncio.Lock()
        async with self._shutdown_lock:
            if self._shutdown_prepared:
                return
            self.sessions.freeze()
            for engine in self.engines or []:
                await engine.taskManager.cancel_all()
            await self._requeue_scheduler_inflight()
            await self._persist_scheduler_sessions()
            await self._cleanup_scheduler_state()
            self.stop_event.set()
            self._shutdown_prepared = True

    async def _close_runtime_state(self):
        if self._runtime_close_lock is None:
            self._runtime_close_lock = asyncio.Lock()
        async with self._runtime_close_lock:
            if self._runtime_closed:
                return
            if self._process_task_manager is not None:
                await self._process_task_manager.close()
            await self.sessions.close_all()
            await self.signalManager.stop()
            self._runtime_closed = True

    async def _persist_scheduler_sessions(self):
        if (
            not self.settings.SCHEDULER_PERSIST
            or not self.settings.SCHEDULER_PERSIST_SESSIONS
            or not self.resources.redis
        ):
            return
        for spider in self.spiders or []:
            scheduler = self.schedulers.get(spider.name)
            persist = getattr(scheduler, "persist_all_sessions", None)
            if persist:
                await persist(spider)

    async def _requeue_scheduler_inflight(self):
        for spider in self.spiders or []:
            scheduler = self.schedulers.get(spider.name)
            requeue = getattr(scheduler, "requeue_inflight", None)
            if requeue:
                await requeue(spider)

    async def _cleanup_scheduler_state(self):
        if self.settings.SCHEDULER_PERSIST:
            return
        cleaned = getattr(self, "_cleaned_scheduler_state", set())
        for spider in self.spiders or []:
            if spider.name in cleaned:
                continue
            scheduler = self.schedulers.get(spider.name)
            cleanup_operations = []
            broker_cleanup = getattr(scheduler, "cleanup", None)
            if broker_cleanup:
                cleanup_operations.append(("broker", broker_cleanup(spider)))
            redis_cleanup = getattr(scheduler, "cleanup_redis_state", None)
            if redis_cleanup:
                cleanup_operations.append(("redis", redis_cleanup(spider)))

            if cleanup_operations:
                results = await asyncio.gather(
                    *(operation for _, operation in cleanup_operations),
                    return_exceptions=True,
                )
                cleanup_succeeded = True
                for (backend, _), result in zip(cleanup_operations, results):
                    if isinstance(result, BaseException):
                        cleanup_succeeded = False
                        self.logger.error(
                            "Failed to clean transient %s state for spider %s: %r",
                            backend,
                            spider.name,
                            result,
                        )
                if cleanup_succeeded:
                    cleaned.add(spider.name)
            else:
                cleaned.add(spider.name)
        self._cleaned_scheduler_state = cleaned

    async def shutdown(self):
        # Stop managed work while broker writes are still allowed. This method
        # can race with start_engines() after Ctrl+C or an external shutdown,
        # so the writable phase is locked and idempotent.
        await self._prepare_shutdown()
        self.taskManager.tasks_done_event.set()
        self.taskManager.error_event.set()

        await self._close_runtime_state()

        # start_engines() sets stop_event after normal completion. Run the same
        # idempotent broker cleanup here so normal exit and Ctrl+C behave alike.
        await self._cleanup_scheduler_state()

        if self.resources:
            await self.resources.close()

__all__ = ["Crawler"]
