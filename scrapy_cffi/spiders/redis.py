import asyncio
from .base import BaseSpider
from ..core.downloader.internet.request import HttpRequest
from ..databases.redis_ingress import resolve_redis_ingress
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..crawler import Crawler
    from ..databases.redis import RedisStreamMessage

class RedisSpider(BaseSpider):
    name = "redisSpider"
    wait_for_start_requests = True
    redis_key = "redis_key"
    redis_start_mode = "list"       # list or stream
    redis_group = None              # stream consumer group name; redis_xgroup is also supported
    redis_consumer = None           # defaults to spider.name; redis_xconsumer is also supported
    redis_stream_field = "data"     # XADD redis_key * data "https://example.com"
    redis_stream_count = 1
    redis_stream_block_ms = 2000
    redis_stream_group_start_id = "0"
    redis_stream_read_id = ">"
    redis_stream_mkstream = True
    redis_stream_ack = True

    def get_redis_ingress_config(self):
        """Resolved ingress config (spider attrs + settings.REDIS_STREAM_INFO)."""
        return resolve_redis_ingress(spider=self, settings=self.settings)

    async def start(self, *args, **kwargs):
        ingress = self.get_redis_ingress_config()
        while not self.stop_event.is_set():
            get_req_task = asyncio.create_task(self.hooks.scheduler.get_start_req(spider=self))
            stop_task = asyncio.create_task(self.stop_event.wait())
            done, pending = await asyncio.wait(
                {get_req_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if stop_task in done:
                break
            if get_req_task in done:
                data = get_req_task.result()
                if not data:
                    await asyncio.sleep(1)
                    continue
                stream_message = self._get_stream_message(data)
                if stream_message:
                    data = stream_message.data
                request = await self.make_request_from_data(data)
                if request:
                    if not stream_message or ingress.auto_ack:
                        self.hooks.scheduler.attach_start_req(
                            request=request,
                            message=stream_message or data,
                        )
                    yield request
                elif stream_message and ingress.auto_ack:
                    await self.hooks.scheduler.ack_start_req(spider=self, message=stream_message)

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

    def _get_stream_message(self, data):
        if hasattr(data, "message_id") and hasattr(data, "data") and hasattr(data, "fields"):
            return data
        return None
