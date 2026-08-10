import asyncio
from ..hooks import pipelines_hooks
from typing import TYPE_CHECKING, Union, Dict
if TYPE_CHECKING:
    from ..item import Item
    from ..crawler import Crawler
    from ..spiders import Spider
    from ..service import ResourceService
    from ..settings import SettingsInfo
    from ..hooks.pipelines import PipelinesHooks

class Pipeline:
    def __init__(
        self, 
        stop_event: asyncio.Event=None,
        settings: "SettingsInfo"=None, 
        resources: "ResourceService"=None,
        hooks: "PipelinesHooks"=None
    ):
        self.stop_event = stop_event
        self.settings = settings
        self.resources = resources
        self.hooks = hooks
        from ..utils.log import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)
        if resources and resources.kafka:
            from ..utils.log import KafkaLoggingHandler
            kafka_handler = KafkaLoggingHandler(kafka=resources.kafka, stop_event=self.stop_event).create_fmt(self.settings)
            self.logger.addHandler(kafka_handler)

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            settings=crawler.settings,
            resources=crawler.resources,
            hooks=pipelines_hooks(crawler)
        )

    async def open_spider(self, spider: "Spider"):
        pass

    async def process_item(self, item: Union["Item", Dict], spider: "Spider"):
        return item

    async def close_spider(self, spider: "Spider"):
        pass
