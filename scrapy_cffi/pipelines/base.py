from ..hooks import pipelines_hooks
from typing import TYPE_CHECKING, Union, Dict
if TYPE_CHECKING:
    from ..item import Item
    from ..crawler import Crawler
    from ..spiders import Spider
    from ..databases import RedisManager
    from ..models.api import SettingsInfo
    from ..hooks.pipelines import PipelinesHooks

class Pipeline:
    def __init__(
        self, 
        settings: "SettingsInfo"=None, 
        redisManager: "RedisManager"=None, 
        hooks: "PipelinesHooks"=None
    ):
        self.settings = settings
        from ..utils import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)
        self.redisManager = redisManager
        self.hooks = hooks

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            settings=crawler.settings,
            redisManager=crawler.redisManager,
            hooks=pipelines_hooks(crawler)
        )

    async def open_spider(self, spider: "Spider"):
        pass

    async def process_item(self, item: Union["Item", Dict], spider: "Spider"):
        return item

    async def close_spider(self, spider: "Spider"):
        pass