import json, asyncio, sys
from .core.api import *
from .interceptors import ChainManager, InterruptibleChainManager
# from .interceptors import DownloadInterceptor
from .interceptors.api import UpdateRequestSpiderInterceptor, RobotSpiderInterceptor
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
        self.sessions_lock = None

        self.redisManager = None
        self.mysqlManager = None
        self.postgresManager = None
        self.mongodbManager = None
        self.rabbitmqManager = None
        self.kafkaManager = None

        self.logger: "Logger" = None
        self.signalManager = None
        self.robot = None
        self.extensions_list = []

        self.spiders = None
        self.engines = None

    @property
    def scheduler(self):
        """When exactly one spider is loaded, exposes its scheduler for legacy code paths."""
        if len(self.schedulers) == 1:
            return next(iter(self.schedulers.values()))
        return None

    def init_output(self, class_list):
        return [get_class_name(it) for it in class_list] if isinstance(class_list, list) else [get_class_name(class_list)]

    async def do_initialization(self, settings: "SettingsInfo", start_type=0):
        self.stop_event = asyncio.Event()

        self.settings: "SettingsInfo" = settings
        from .cpy import CExtensionLoader
        from .models.api import CPYExtension

        framework_cpy = [
            CPYExtension(module_name="bloom")
        ]
        framework_cpy.extend(self.settings.CPY_EXTENSIONS.RESOURCES) # User first principle, same name can cover framework modules
        self.settings.CPY_EXTENSIONS.RESOURCES = framework_cpy
        CExtensionLoader(resource_dir=self.settings.CPY_EXTENSIONS.DIR).load_all(configs=self.settings.CPY_EXTENSIONS.RESOURCES)

        self.global_lock = async_context_factory(
            max_tasks=self.settings.MAX_GLOBAL_CONCURRENT_TASKS,
            semaphore_cls=asyncio.BoundedSemaphore
        )

        # if not logger: # To ensure log stability, it is no longer enabled
        from .utils.log import init_logger, KafkaLoggingHandler
        logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)
        self.logger = logger
        # kafka
        if self.settings.KAFKA_INFO.resolved_url:
            from .mq.kafka import KafkaManager
            self.kafkaManager = KafkaManager.from_crawler(self)
            kafka_handler = KafkaLoggingHandler(kafka=self.kafkaManager, stop_event=self.stop_event).create_fmt(self.settings)
            self.logger.addHandler(kafka_handler)

        self.sessions_lock = asyncio.Lock()
        self.sessions = SessionManager.from_crawler(self)
        self.signalManager = SignalManager.from_crawler(self)
        self.robot = RobotsManager.from_crawler(self)
        
        # redis
        if self.settings.REDIS_INFO.resolved_url:
            from .databases import RedisManager
            self.redisManager = RedisManager.from_crawler(self)

        # mysql
        if self.settings.MYSQL_INFO.resolved_url:
            from .databases.mysql import SQLAlchemyMySQLManager
            self.mysqlManager = SQLAlchemyMySQLManager.from_crawler(self)
            await self.mysqlManager.init()

        # postgres
        if self.settings.POSTGRES_INFO.resolved_url:
            from .databases.postgres import SQLAlchemyPostgresManager
            self.postgresManager = SQLAlchemyPostgresManager.from_crawler(self)
            await self.postgresManager.init()

        # mongodb
        if self.settings.MONBODB_INFO.resolved_url:
            from .databases.mongodb import MongoDBManager
            self.mongodbManager = MongoDBManager.from_crawler(self)

        # rabbitmq
        if self.settings.RABBITMQ_INFO.resolved_url:
            from .mq.rabbitmq import RabbitMQManager
            self.rabbitmqManager = RabbitMQManager.from_crawler(self)
            if not self.settings.SCHEDULER:
                self.settings.SCHEDULER = "scrapy_cffi.scheduler.RabbitMqScheduler"

        self.settings.SPIDER_INTERCEPTORS_PATH.value.extend([RobotSpiderInterceptor, UpdateRequestSpiderInterceptor])
        self.spiderInterceptor_chain = InterruptibleChainManager.from_crawler(self, class_list=self.settings.SPIDER_INTERCEPTORS_PATH.value)

        # self.settings.DOWNLOAD_INTERCEPTORS_PATH.value.insert(0, DownloadInterceptor)
        self.downloadInterceptor_chain = InterruptibleChainManager.from_crawler(self, class_list=self.settings.DOWNLOAD_INTERCEPTORS_PATH.value)

        self.settings.ITEM_PIPELINES_PATH.value.insert(0, Pipeline)
        self.pipelines_chain = ChainManager.from_crawler(self, class_list=self.settings.ITEM_PIPELINES_PATH.value)

        from .hooks import signals_hooks
        for ext_cls in self.settings.EXTENSIONS_PATH.value:
            self.extensions_list.append(ext_cls.from_crawler(
                hooks=signals_hooks(self), 
                redisManager=self.redisManager,
                mysqlManager=self.mysqlManager,
                postgresManager=self.postgresManager,
                mongodbManager=self.mongodbManager,
                rabbitmqManager=self.rabbitmqManager,
                kafkaManager=self.kafkaManager,
        ))

        self.downloader = Downloader.from_crawler(self)

        # spider start type
        if not self.settings.SPIDERS_PATH:
            self.settings.SPIDERS_PATH = str(self.run_py_dir / "spiders")
            self.logger.warning(f"not provided self.settings.SPIDERS_PATH，guessed to load -> {self.settings.SPIDERS_PATH}")
            start_type = 0
        if start_type:
            self.spiders = [load_object(path=self.settings.SPIDERS_PATH)]
        else:
            self.spiders = get_all_spiders_cls(spiders_dir=self.settings.SPIDERS_PATH)
            get_all_spiders_name(logger=self.logger, spiders_cls_list=self.spiders)

        spider_cls_list = self.spiders

        scheduler_path = self.settings.SCHEDULER
        if scheduler_path:
            scheduler_cls = load_object(path=scheduler_path)
        else:
            from .core.scheduler import Scheduler
            scheduler_cls = Scheduler

        self.schedulers.clear()
        for spider_cls in spider_cls_list:
            name = spider_cls.name
            spider_settings = merge_spider_settings(self.settings, spider_cls)
            self.schedulers[name] = scheduler_cls.from_crawler(
                self,
                spiders_name=[name],
                spider_classes=[spider_cls],
                settings=spider_settings,
            )

        for spider_cls in spider_cls_list:
            has_redis_key = getattr(spider_cls, "redis_key", None)
            if has_redis_key:
                self.taskManager = TaskManager.from_crawler(self, is_distributed=True) # Shared by all spider engines; if any exist, start one to handle blocking
                break
        else:
            self.taskManager = TaskManager.from_crawler(self, is_distributed=False)

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
        self.stop_event.set()
        await self.sessions.close_all()
        await self.signalManager.stop()

    async def shutdown(self):
        self.stop_event.set()
        self.taskManager.tasks_done_event.set()
        self.taskManager.error_event.set()

        # await asyncio.sleep(1)
        for engine in self.engines:
            await engine.taskManager.cancel_all()
        await self.sessions.close_all()
        await self.signalManager.stop()

        if not self.settings.SCHEDULER_PERSIST and self.redisManager:
            for spider in self.spiders:
                if getattr(spider, "redis_key", None):
                    await self.redisManager.delete(spider.redis_key)
                sch = self.schedulers.get(spider.name)
                if sch is None:
                    continue
                if getattr(sch, "is_distributed", False):
                    await self.redisManager.delete(sch.get_queue_key(spider))
                df = getattr(sch, "dupefilter", None)
                if df is not None:
                    ns = getattr(df, "new_seen", None)
                    if isinstance(ns, str):
                        await self.redisManager.delete(ns)
                    ss = getattr(df, "sent_seen", None)
                    if isinstance(ss, str):
                        await self.redisManager.delete(ss)
        
        if self.rabbitmqManager:
            await self.rabbitmqManager.close()

        if self.kafkaManager:
            await self.kafkaManager.close()

        if self.mysqlManager:
            await self.mysqlManager.close()

        if self.postgresManager:
            await self.postgresManager.close()

__all__ = ["Crawler"]
