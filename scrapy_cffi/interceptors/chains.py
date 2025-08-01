import types
from ..models import StrictValidatedModel
from enum import Enum
from typing import Optional, TYPE_CHECKING, Union, Dict, List, Callable
from ..spiders import BaseSpider
from ..core.downloader.internet import Request
from ..core.downloader.internet import Response
from ..item import Item
if TYPE_CHECKING:
    from ..interceptors import SpiderInterceptor, DownloadInterceptor
    from ..databases import RedisManager
    from ..crawler import Crawler

class ChainNode:
    def __init__(self, instance):
        self.instance: Union["SpiderInterceptor", "DownloadInterceptor"] = instance
        self.prev: Union["SpiderInterceptor", "DownloadInterceptor"] = None
        self.next: Union["SpiderInterceptor", "DownloadInterceptor"] = None

class ChainManager:
    def __init__(self, crawler: "Crawler", class_list: list):
        self.chain_list: list[ChainNode] = []
        self.chain_head: Optional[ChainNode] = None
        self.chain_tail: Optional[ChainNode] = None
        self.create_chain(crawler, class_list)
        self.settings = crawler.settings
        self.redisManager: "RedisManager" = crawler.redisManager
        from ..utils import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)

    @classmethod
    def from_crawler(cls, crawler: "Crawler", class_list: list):
        return cls(
            crawler=crawler,
            class_list=class_list,
        )

    def create_chain(self, crawler: "Crawler", class_list: list["SpiderInterceptor", "DownloadInterceptor"]):
        nodes: List[ChainNode] = []
        for cls in class_list:
            inst = cls.from_crawler(crawler)
            nodes.append(ChainNode(inst))

        for i, node in enumerate(nodes):
            if i > 0: node.prev = nodes[i-1]
            if i < len(nodes) - 1: node.next = nodes[i+1]

        self.chain_head = nodes[0] if nodes else None
        self.chain_tail = nodes[-1] if nodes else None
        self.chain_list = nodes

    async def forward_pass(self, call_func_cls, call_func_name, pad_data=None, **kwargs):
        node: ChainNode = self.chain_head
        while node:
            call_func_addr = getattr(call_func_cls, call_func_name)
            result = await call_func_addr(pad_data, **kwargs)
            node = node.next
            if node:
                call_func_cls = node.instance
                if result is not None:
                    pad_data = result
        return result

    async def backward_pass(self, call_func_cls, call_func_name, item=None, **kwargs):
        node: ChainNode = self.chain_tail
        while node:
            call_func_addr = getattr(call_func_cls, call_func_name)
            result = await call_func_addr(item, **kwargs)
            node = node.prev
            if node:
                call_func_cls = node.instance
                if result is not None:
                    item = result
        return result
    
class ChainNextEnum(str, Enum):
    RESCHEDULE = "reschedule"
    RESPONSE = "response"
    EXCEPTION = "exception"
    DOWNLOADER = "downloader"
    PIPELINE = "pipeline"
    SPIDER = "spider"

class ChainResult(StrictValidatedModel):
    next: ChainNextEnum
    request: Optional[Request] = None
    response: Optional[Union[Response, BaseException]] = None
    spider: Optional[BaseSpider] = None
    item: Optional[Union[Item, Dict]] = None
    exception: Optional[BaseException] = None
    is_across: int = 0

async def _flatten_asyncgen(value):
    from collections.abc import AsyncIterable, Iterable
    ATOMIC_TYPES = (Request, Item, BaseException, str, bytes, dict, type(None))
    if isinstance(value, AsyncIterable):
        async for v in value:
            async for sub_v in _flatten_asyncgen(v):
                yield sub_v
    elif (
        isinstance(value, Iterable)
        and not isinstance(value, ATOMIC_TYPES)
    ):
        for v in value:
            async for sub_v in _flatten_asyncgen(v):
                yield sub_v
    else:
        if not isinstance(value, ATOMIC_TYPES):
            raise TypeError(f"Unsupported spider return type: {type(value)}")
        yield value

def _ensure_asyncgen(result):
    if isinstance(result, types.CoroutineType):
        async def gen():
            value = await result
            async for item in _flatten_asyncgen(value):
                yield item
        return gen()
    else:
        async def gen():
            async for item in _flatten_asyncgen(result):
                yield item
        return gen()

# Interruptible chain
class InterruptibleChainManager(ChainManager):
    async def request_intercept_chain(self, request: Request, spider, callback: Callable):
        """
        Pass the request through the middleware chain from head to tail.

        For each middleware node:
        - If result is None, continue to next node.
        - If result is a Request, return ChainResult with next step RESCHEDULE and new request.
        - If result is a Response, return ChainResult with next step RESPONSE, passing current request and new response.
        - If result is an Exception, return ChainResult with next step EXCEPTION, passing exception and current request.
        - If result is invalid, raise ValueError.

        If all middleware return None, return ChainResult with next step DOWNLOADER to continue download phase.

        Returns:
            ChainResult directing the next step of processing.
        """
        node = self.chain_head
        while node:
            result = await node.instance.request_intercept(request=request, spider=spider)
            if result is None:
                node = node.next
                continue
            elif isinstance(result, Request):
                return await callback(ChainResult(next=ChainNextEnum.RESCHEDULE, request=result, spider=spider))
            elif isinstance(result, Response):
                return await callback(ChainResult(next=ChainNextEnum.RESPONSE, request=request, response=result, spider=spider))
            elif isinstance(result, BaseException):
                return await callback(ChainResult(next=ChainNextEnum.EXCEPTION, exception=result, request=request, spider=spider))
            raise callback(ValueError("request_intercept_chain got invalid return"))
        return await callback(ChainResult(next=ChainNextEnum.DOWNLOADER, request=request, spider=spider))
    
    async def response_intercept_chain(self, request: Request, response: Response, spider, callback: Callable):
        """
        Pass the response through the middleware chain from tail to head.

        For each middleware node:
        - If result is a Response, update response and continue to previous node.
        - If result is a Request, return ChainResult with next step RESCHEDULE and new request.
        - If result is an Exception, return ChainResult with next step EXCEPTION and exception.
        - If result is invalid, raise ValueError.

        If all middleware return None or Response, return ChainResult with next step SPIDER to proceed spider processing.

        Returns:
            ChainResult directing the next step of processing.
        """
        node = self.chain_tail
        while node:
            result = await node.instance.response_intercept(request=request, response=response, spider=spider)
            if result is not None:
                if isinstance(result, Response):
                    node = node.prev
                    response = result
                    continue
                elif isinstance(result, Request):
                    return await callback(ChainResult(next=ChainNextEnum.RESCHEDULE, request=result, spider=spider))
                elif isinstance(result, BaseException):
                    return await callback(ChainResult(next=ChainNextEnum.EXCEPTION, exception=result, request=request, spider=spider))
            raise ValueError("response_intercept_chain got invalid return")
        return await callback(ChainResult(next=ChainNextEnum.SPIDER, response=response, request=request, spider=spider))
    
    async def exception_intercept_chain(self, request: Request, exception: BaseException, spider, callback:  Callable, is_across=0):
        """
        Pass the exception through the middleware chain from tail to head for handling.

        For each middleware node:
        - If result is None, continue to previous node.
        - If result is an Exception, update exception and continue.
        - If result is a Request, return ChainResult with next step RESCHEDULE and new request.
        - If result is a Response, return ChainResult with next step SPIDER and new response.
        - If result is invalid, raise ValueError.

        If all middleware return None or Exception, return ChainResult with next step SPIDER with current exception.

        Args:
            is_across (int): flag indicating if the exception is propagated across middlewares.

        Returns:
            ChainResult directing the next step of processing.
        """
        node = self.chain_tail
        while node:
            result = await node.instance.exception_intercept(request=request, exception=exception, spider=spider)
            if result is None:
                node = node.prev
                continue
            elif isinstance(result, BaseException):
                node = node.prev
                exception = result
                continue
            elif isinstance(result, Request):
                return await callback(ChainResult(next=ChainNextEnum.RESCHEDULE, request=result, spider=spider, is_across=is_across))
            elif isinstance(result, Response):
                return await callback(ChainResult(next=ChainNextEnum.SPIDER, response=result, request=request, spider=spider, is_across=is_across))
            raise ValueError("exception_intercept_chain got invalid return")
        return await callback(ChainResult(next=ChainNextEnum.SPIDER, response=result, request=request, spider=spider, is_across=is_across))
    
    async def process_spider_input_chain(self, response: Response, request: Request, spider, callback: Callable):
        """
        Pass the response through the spider input middleware chain sequentially.

        For each middleware node:
        - If the result is None, continue to the next node.
        - If the result is an exception, wrap it as a ChainResult with next step to spider's errback.
        - If the result is invalid (not None or Exception), raise an error.

        If all middlewares return None, wrap the original response as ChainResult directing to spider's callback.

        Returns:
            ChainResult object directing next processing step.
        """
        node = self.chain_head
        while node:
            result = await node.instance.process_spider_input(response=response, spider=spider)
            if result is None:
                node = node.next
                continue
            elif isinstance(result, BaseException):
                return await callback(ChainResult(next=ChainNextEnum.SPIDER, response=result, request=request, spider=spider)) # Pass to spider errback)
            raise ValueError("process_spider_input_chain got invalid return")
        return await callback(ChainResult(next=ChainNextEnum.SPIDER, response=response, request=request, spider=spider)) # Pass to spider callback
    
    async def process_spider_output_chain(self, response: Response=None, result=None, spider=None):
        """
        Process the spider output through the middleware chain in reverse order (from tail to head).

        Workflow:
        1. Wrap the initial `result` into an async generator to uniformly handle single or multiple results.
        2. For each item yielded from the current results:
        - Pass it through each middleware node in reverse order.
        - At each node, call `process_spider_output` with the current item.
        - The middleware's output may be:
            - None: skip to the previous middleware node with the same item.
            - Single or multiple items: wrap as an async generator and iterate over them.
            - Each yielded item is processed similarly, ensuring a flat iteration.
        - If an Exception is yielded at any point, emit a ChainResult with EXCEPTION and stop processing.
        3. After passing through all middleware nodes, yield final ChainResult objects according to the processed item type:
        - Request: yield RESCHEDULE to retry the request.
        - Item or dict: yield PIPELINE to send the item downstream.
        - None: ignore.
        - Other unsupported types: raise ValueError.

        This design guarantees that the middleware chain can handle any combination of single or multiple results returned by each middleware,
        while keeping each middleware focused on processing individual items.
        """
        node = self.chain_tail
        while node:
            processed = await node.instance.process_spider_output(response=response, result=result, spider=spider)
            if processed is None:
                node = node.prev
                continue
            is_error = False
            async for i in _ensure_asyncgen(processed):
                if isinstance(i, (Request, Item, dict)):
                    result = i
                elif isinstance(i, BaseException):
                    result = i
                    yield ChainResult(next=ChainNextEnum.EXCEPTION, response=response, exception=result, spider=spider)
                    is_error = True
                    return
                else:
                    pass
                    # return f"Unsupported spider return type: {type(i)}"
            if not is_error:
                node = node.prev
        if result is None:
            pass
        elif isinstance(result, Request):
            yield ChainResult(next=ChainNextEnum.RESCHEDULE, request=result, spider=spider)
        elif isinstance(result, (Item, dict)):
            yield ChainResult(next=ChainNextEnum.PIPELINE, item=result, spider=spider)
        else:
            raise ValueError(f"Unsupported spider return type: {type(result)}")
    
    async def process_spider_exception_chain(self, response: Response, exception: BaseException, spider, callback: Callable, is_across=0):
        """
        Pass the exception through the spider exception middleware chain from tail to head.

        For each middleware node:
        - If result is None, continue to previous node.
        - If result is an Exception, immediately return ChainResult with next step EXCEPTION, passing original response and exception.
        - If result is a Request, return ChainResult with next step RESCHEDULE and new request.
        - If result is an Item or dict, return ChainResult with next step PIPELINE and the item.
        - If result is invalid, raise ValueError.

        If all middleware return None, return ChainResult with next step EXCEPTION passing current response and exception.

        Args:
            is_across (int): flag indicating if the exception handling is propagated across middlewares.

        Returns:
            ChainResult directing the next step of processing.
        """
        node = self.chain_tail
        while node:
            result = await node.instance.process_spider_exception(response=response, exception=exception, spider=spider)
            if result is None:
                node = node.prev
                continue
            elif isinstance(result, BaseException):
                return await callback(ChainResult(next=ChainNextEnum.EXCEPTION, response=response, exception=exception, spider=spider, is_across=is_across))
            elif isinstance(result, Request):
                return await callback(ChainResult(next=ChainNextEnum.RESCHEDULE, request=result, spider=spider, is_across=is_across))
            elif isinstance(result, (Item, dict)):
                return await callback(ChainResult(next=ChainNextEnum.PIPELINE, item=result, spider=spider, is_across=is_across))
            raise ValueError("process_spider_exception_chain got invalid return")
        return await callback(ChainResult(next=ChainNextEnum.EXCEPTION, response=response, exception=exception, spider=spider, is_across=is_across))

__all__ = [
    "ChainManager",
    "InterruptibleChainManager"
]