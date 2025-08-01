from scrapy_cffi.extensions import signals, Extension
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from scrapy_cffi.hooks.signals import SignalsHooks
    from scrapy_cffi.models.api import SingalInfo

class CustomExtension(Extension):
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

    async def engine_started(self, data: "SingalInfo"):
        print(f'CustomExtension -> engine started: {data.signal_time}')

    async def engine_stopped(self, data: "SingalInfo"):
        print(f'CustomExtension -> engine stopped: {data.signal_time}')

    async def scheduler_empty(self, data: "SingalInfo"):
        print(f'CustomExtension -> scheduler empty: {data.signal_time}')

    async def task_error(self, data: "SingalInfo"):
        print(f'CustomExtension -> task error: {data.reason}, signal_time：{data.signal_time}')

    async def spider_opened(self, data: "SingalInfo"):
        print(f'CustomExtension -> spider opened: {data.spider.name}, start_time: {data.signal_time}')

    async def spider_closed(self, data: "SingalInfo"):
        print(f'CustomExtension -> spider closed: {data.spider.name}, end_time: {data.signal_time}')

    async def spider_error(self, data: "SingalInfo"):
        print(f'CustomExtension -> spider error: {data.spider.name}, exception: {data.exception}, signal_time：{data.signal_time}')

    async def request_scheduled(self, data: "SingalInfo"):
        print(f'CustomExtension -> request scheduled: {data.request.url}, signal_time：{data.signal_time}')

    async def request_dropped(self, data: "SingalInfo"):
        print(f'CustomExtension -> request dropped: {data.request.url}, reason: {data.reason}, signal_time：{data.signal_time}')

    async def request_reached_downloader(self, data: "SingalInfo"):
        print(f'CustomExtension -> request reached downloader: {data.request.url}, signal_time：{data.signal_time}')

    async def response_received(self, data: "SingalInfo"):
        print(f'CustomExtension -> response received: {data.response}, request: {data.request.url}, signal_time：{data.signal_time}')

    async def item_scraped(self, data: "SingalInfo"):
        print(f'CustomExtension -> item scraped: {data.item}, spider_name: {data.spider.name}, signal_time：{data.signal_time}')