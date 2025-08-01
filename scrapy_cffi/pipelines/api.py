from . import Pipeline
from typing import TYPE_CHECKING, Union, Dict
from ..hooks import _pipelines_hooks
if TYPE_CHECKING:
    from ..item import Item
    from ..crawler import Crawler
    from ..spiders import Spider
    from ..hooks.pipelines import _PipelinesHooks
    from ..databases import RedisManager
    from ..models.api import SettingsInfo

class _InnerPipeline(Pipeline):
    def __init__(
        self, 
        settings: "SettingsInfo"=None, 
        redisManager: "RedisManager"=None, 
        hooks: "_PipelinesHooks"=None
    ):
        super().__init__(settings=settings, redisManager=redisManager)
        self.hooks = hooks

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            settings=crawler.settings,
            redisManager=crawler.redisManager,
            hooks=_pipelines_hooks(crawler)
        )

    async def open_spider(self, spider: "Spider"):
        pass

    async def process_item(self, item: Union["Item", Dict], spider: "Spider"):
        if self.settings.RET_COOKIES:
            if item.get("session_end"):
                self.hooks.session.mark_end(item.get("session_id"))
            ret_cookies = await self.hooks.session.session_end_cookies(session_id=item.get("session_id"))
            item[self.settings.RET_COOKIES] = ret_cookies
        self.logger.debug(f"[PIPELINE] Processing item: {item}")
        return item

    async def close_spider(self, spider: "Spider"):
        # self.logger.debug(f"[PIPELINE] {spider.__class__.name} closed.")
        pass
