import asyncio
from .base import Pipeline
from typing import TYPE_CHECKING, Union, Dict
from ..hooks import _pipelines_hooks
if TYPE_CHECKING:
    from ..item import Item
    from ..crawler import Crawler
    from ..spiders import Spider
    from ..hooks.pipelines import _PipelinesHooks
    from ..databases import RedisManager
    from ..databases.mysql import SQLAlchemyMySQLManager
    from ..databases.mongodb import MongoDBManager
    from ..mq.rabbitmq import RabbitMQManager
    from ..mq.kafka import KafkaManager
    from ..settings import SettingsInfo

class _InnerPipeline(Pipeline): # scrapy_cffi version 0.1.x
    def __init__(
        self, 
        stop_event: asyncio.Event=None,
        settings: "SettingsInfo"=None, 
        redisManager: "RedisManager"=None, 
        mysqlManager: "SQLAlchemyMySQLManager"=None,
        mongodbManager: "MongoDBManager"=None,
        rabbitmqManager: "RabbitMQManager"=None,
        kafkaManager: "KafkaManager"=None,
        hooks: "_PipelinesHooks"=None
    ):
        super().__init__(
            stop_event=stop_event,
            settings=settings, 
            redisManager=redisManager,
            mysqlManager=mysqlManager,
            mongodbManager=mongodbManager,
            rabbitmqManager=rabbitmqManager,
            kafkaManager=kafkaManager,
        )
        self.hooks = hooks

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            settings=crawler.settings,
            redisManager=crawler.redisManager,
            mysqlManager=crawler.mysqlManager,
            mongodbManager=crawler.mongodbManager,
            rabbitmqManager=crawler.rabbitmqManager,
            kafkaManager=crawler.kafkaManager,
            hooks=_pipelines_hooks(crawler)
        )

    async def open_spider(self, spider: "Spider"):
        pass

    async def process_item(self, item: Union["Item", Dict], spider: "Spider"):
        if self.settings.RET_COOKIES:
            if item.get("session_end"):
                self.hooks.session.mark_end(item.get("session_id"))
            ret_cookies = self.hooks.session.get_session_cookies(session_id=item.get("session_id"))
            item[self.settings.RET_COOKIES] = ret_cookies
        self.logger.debug(f"[PIPELINE] Processing item: {item}")
        return item

    async def close_spider(self, spider: "Spider"):
        # self.logger.debug(f"[PIPELINE] {spider.__class__.name} closed.")
        pass
