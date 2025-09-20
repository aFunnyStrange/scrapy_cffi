import asyncio
from . import BaseSpider
from ..core.downloader.internet.request import HttpRequest
from ..hooks import spiders_hooks
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..core.scheduler.api import RedisScheduler
    from ..crawler import Crawler

class RedisSpider(BaseSpider):
    name = "redisSpider"
    redis_key = "redis_key"

    def __init__(self, 
        settings=None, 
        run_py_dir=None, 
        stop_event=None, 
        session_id="", 
        hooks=None,
        redisScheduler=None, 
        *args, **kwargs
    ):
        super().__init__(
            settings=settings, 
            run_py_dir=run_py_dir, 
            stop_event=stop_event, 
            session_id=session_id,
            hooks=hooks,
            *args, **kwargs
        )
        self.redisScheduler: "RedisScheduler" = redisScheduler

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            settings=crawler.settings,
            run_py_dir=crawler.run_py_dir,
            stop_event=crawler.stop_event,
            session_id="",
            hooks=spiders_hooks(crawler),
            redisScheduler=crawler.scheduler
        )

    async def start(self, *args, **kwargs):
        while not self.stop_event.is_set():
            get_req_task = asyncio.create_task(self.redisScheduler.get_start_req(spider=self))
            stop_task = asyncio.create_task(self.stop_event.wait())
            done, pending = await asyncio.wait(
                {get_req_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED
            )
            if stop_task in done:
                get_req_task.cancel()
                try:
                    await get_req_task
                except asyncio.CancelledError:
                    pass
                break
            if get_req_task in done:
                data = get_req_task.result()
                if not data:
                    await asyncio.sleep(1)
                    continue
                request = await self.make_request_from_data(data)
                if request:
                    yield request

    # By default, only a URL is expected. If data is in JSON format, this method should be overridden in subclasses.
    async def make_request_from_data(self, data: bytes):
        return HttpRequest(
            url=data.decode('utf-8'),
            method="GET",
            headers=self.settings.DEFAULT_HEADERS,
            cookies=self.settings.DEFAULT_COOKIES,
            proxies=self.settings.PROXIES,
            timeout=self.settings.TIMEOUT,
            dont_filter=self.settings.DONT_FILTER,
            callback=self.parse, 
            errback=self.errRet
        )