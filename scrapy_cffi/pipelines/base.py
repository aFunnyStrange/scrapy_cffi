import asyncio
from ..hooks import pipelines_hooks
from typing import TYPE_CHECKING, Union, Dict
if TYPE_CHECKING:
    from ..item import Item
    from ..crawler import Crawler
    from ..spiders import Spider
    from ..databases import RedisManager
    from ..databases.mysql import SQLAlchemyMySQLManager
    from ..databases.mongodb import MongoDBManager
    from ..settings import SettingsInfo
    from ..hooks.pipelines import PipelinesHooks
    from ..mq.rabbitmq import RabbitMQManager
    from ..mq.kafka import KafkaManager

class Pipeline:
    def __init__(
        self, 
        stop_event: asyncio.Event=None,
        settings: "SettingsInfo"=None, 
        redisManager: "RedisManager"=None, 
        mysqlManager: "SQLAlchemyMySQLManager"=None,
        mongodbManager: "MongoDBManager"=None,
        rabbitmqManager: "RabbitMQManager"=None,
        kafkaManager: "KafkaManager"=None,
        hooks: "PipelinesHooks"=None
    ):
        self.stop_event = stop_event
        self.settings = settings
        self.redisManager = redisManager
        self.mysqlManager = mysqlManager
        self.mongodbManager = mongodbManager
        self.rabbitmqManager = rabbitmqManager
        self.kafkaManager = kafkaManager
        self.hooks = hooks
        from ..utils import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)
        if kafkaManager:
            from ..utils import KafkaLoggingHandler
            kafka_handler = KafkaLoggingHandler(kafka=self.kafkaManager, stop_event=self.stop_event).create_fmt(self.settings)
            self.logger.addHandler(kafka_handler)

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
            hooks=pipelines_hooks(crawler)
        )

    async def open_spider(self, spider: "Spider"):
        pass

    async def process_item(self, item: Union["Item", Dict], spider: "Spider"):
        return item

    async def close_spider(self, spider: "Spider"):
        pass