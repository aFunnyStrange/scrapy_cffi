import asyncio
from typing import Union
from ..spiders import Spider
from ..item import Item
from ..hooks import interceptors_hooks
from ..core.downloader.internet import *
from typing import TYPE_CHECKING, Dict
if TYPE_CHECKING:
    from ..crawler import Crawler
    from ..hooks.interceptors import InterceptorsHooks
    from ..models.api import SettingsInfo

class BaseInterceptor:
    def __init__(
        self, 
        stop_event: asyncio.Event=None, 
        settings: "SettingsInfo"=None, 
        **kwargs
    ):
        self.stop_event = stop_event
        self.settings = settings
        self.kwargs = kwargs

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            settings=crawler.settings,
        )

class DownloadInterceptor(BaseInterceptor):
    RequestType = Union[HttpRequest, WebSocketRequest]
    ResponseType = Union[HttpResponse, WebSocketResponse]

    async def request_intercept(self, request: RequestType, spider: Spider):
        return None

    async def response_intercept(self, request: RequestType, response: ResponseType, spider: Spider):
        return response
    
    async def exception_intercept(self, request: RequestType, exception: BaseException, spider: Spider):
        return exception
    
class SpiderInterceptor(BaseInterceptor):
    ResponseType = Union[HttpResponse, WebSocketResponse]
    ResultType = Union[Request, Item, Dict, None]
    async def process_spider_input(self, response: ResponseType, spider: Spider):
        return None

    async def process_spider_output(self, response: ResponseType, result: ResultType, spider: Spider):
        return result
    
    async def process_spider_exception(self, response: ResponseType, exception: BaseException, spider: Spider):
        return None

class _InnerSpiderInterceptor(SpiderInterceptor):
    def __init__(self,  
        stop_event: asyncio.Event=None, 
        settings: "SettingsInfo"=None, 
        hooks: "InterceptorsHooks"=None, 
        sessions_lock: asyncio.Lock=None, 
        **kwargs
    ):
        super().__init__(stop_event=stop_event, settings=settings, **kwargs)
        self.hooks = hooks
        self.sessions_lock = sessions_lock

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            settings=crawler.settings,
            hooks=interceptors_hooks(crawler),
            sessions_lock=crawler.sessions_lock
        )