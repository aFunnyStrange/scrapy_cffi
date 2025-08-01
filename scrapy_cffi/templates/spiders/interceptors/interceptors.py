from scrapy_cffi.interceptors import DownloadInterceptor
from scrapy_cffi.internet import *
from typing import Union, TYPE_CHECKING
if TYPE_CHECKING:
    from scrapy_cffi.spiders import BaseSpider

class CustomDownloadInterceptor1(DownloadInterceptor):
    RequestType = Union[HttpRequest, WebSocketRequest]
    ResponseType = Union[HttpResponse, WebSocketResponse]

    async def request_intercept(self, request: RequestType, spider: "BaseSpider"):
        return None

    async def response_intercept(self, request: RequestType, response: ResponseType, spider: "BaseSpider"):
        return response
    
    async def exception_intercept(self, request: RequestType, exception: BaseException, spider: "BaseSpider"):
        return exception
    
class CustomDownloadInterceptor2(DownloadInterceptor):
    RequestType = Union[HttpRequest, WebSocketRequest]
    ResponseType = Union[HttpResponse, WebSocketResponse]

    async def request_intercept(self, request: RequestType, spider: "BaseSpider"):
        return None

    async def response_intercept(self, request: RequestType, response: ResponseType, spider: "BaseSpider"):
        return response
    
    async def exception_intercept(self, request: RequestType, exception: BaseException, spider: "BaseSpider"):
        return exception