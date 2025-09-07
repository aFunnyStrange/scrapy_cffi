import asyncio
import functools
import json
from ..extensions import signals, Extension
from typing import TYPE_CHECKING, Callable, Awaitable, Any
if TYPE_CHECKING:
    from scrapy_cffi.hooks.signals import SignalsHooks
    from scrapy_cffi.models.api import SingalInfo

def locked(method: Callable[..., Awaitable[Any]]):
    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        async with self.lock:
            return await method(self, *args, **kwargs)
    return wrapper

class StatisticsExtension(Extension):
    count = {
        "engine_started": 0,
        "engine_stopped": 0,
        "scheduler_empty": 0,
        "task_error": 0,
        "spider_opened": 0,
        "spider_closed": 0,
        "spider_error": 0,
        "request_scheduled": 0,
        "request_dropped": 0,
        "request_reached_downloader": 0,
        "response_received": 0,
        "item_scraped": 0,
    }
    lock = asyncio.Lock()

    @classmethod
    def from_crawler(cls, hooks: "SignalsHooks"):
        extension_cls = cls(hooks)
        hooks.signals.connect(signals.engine_started, extension_cls.engine_started)
        hooks.signals.connect(signals.engine_stopped, extension_cls.engine_stopped)
        hooks.signals.connect(signals.scheduler_empty, extension_cls.scheduler_empty)
        hooks.signals.connect(signals.task_error, extension_cls.task_error)
        hooks.signals.connect(signals.spider_opened, extension_cls.spider_opened)
        hooks.signals.connect(signals.spider_closed, extension_cls.spider_closed)
        hooks.signals.connect(signals.spider_error, extension_cls.spider_error)
        hooks.signals.connect(signals.request_scheduled, extension_cls.request_scheduled)
        hooks.signals.connect(signals.request_dropped, extension_cls.request_dropped)
        hooks.signals.connect(signals.request_reached_downloader, extension_cls.request_reached_downloader)
        hooks.signals.connect(signals.response_received, extension_cls.response_received)
        hooks.signals.connect(signals.item_scraped, extension_cls.item_scraped)
        return extension_cls

    @locked
    async def engine_started(self, data: "SingalInfo"):
        self.count["engine_started"] += 1
        print(json.dumps(self.count, indent=4, ensure_ascii=False))

    @locked
    async def engine_stopped(self, data: "SingalInfo"):
        self.count["engine_stopped"] += 1
        print(json.dumps(self.count, indent=4, ensure_ascii=False))

    @locked
    async def scheduler_empty(self, data: "SingalInfo"):
        self.count["scheduler_empty"] += 1
        print(json.dumps(self.count, indent=4, ensure_ascii=False))

    @locked
    async def task_error(self, data: "SingalInfo"):
        self.count["task_error"] += 1
        print(json.dumps(self.count, indent=4, ensure_ascii=False))

    @locked
    async def spider_opened(self, data: "SingalInfo"):
        self.count["spider_opened"] += 1
        print(json.dumps(self.count, indent=4, ensure_ascii=False))

    @locked
    async def spider_closed(self, data: "SingalInfo"):
        self.count["spider_closed"] += 1
        print(json.dumps(self.count, indent=4, ensure_ascii=False))

    @locked
    async def spider_error(self, data: "SingalInfo"):
        self.count["spider_error"] += 1
        print(json.dumps(self.count, indent=4, ensure_ascii=False))

    @locked
    async def request_scheduled(self, data: "SingalInfo"):
        self.count["request_scheduled"] += 1
        print(json.dumps(self.count, indent=4, ensure_ascii=False))

    @locked
    async def request_dropped(self, data: "SingalInfo"):
        self.count["request_dropped"] += 1
        print(json.dumps(self.count, indent=4, ensure_ascii=False))

    @locked
    async def request_reached_downloader(self, data: "SingalInfo"):
        self.count["request_reached_downloader"] += 1
        print(json.dumps(self.count, indent=4, ensure_ascii=False))

    @locked
    async def response_received(self, data: "SingalInfo"):
        self.count["response_received"] += 1
        print(json.dumps(self.count, indent=4, ensure_ascii=False))

    @locked
    async def item_scraped(self, data: "SingalInfo"):
        self.count["item_scraped"] += 1
        print(json.dumps(self.count, indent=4, ensure_ascii=False))