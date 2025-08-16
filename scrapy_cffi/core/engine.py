import asyncio, time
from ..extensions import signals
from ..models.api import SingalInfo
from .downloader import *
from ..exceptions import DownloadError
from ..interceptors import ChainResult, ChainNextEnum
from ..interceptors.chains import _ensure_asyncgen
from typing import TYPE_CHECKING, Dict, Union
if TYPE_CHECKING:
    from ..crawler import Crawler
    from .tasks import TaskManager
    from .scheduler import Scheduler
    from ..extensions import SignalManager
    from ..models.api import SettingsInfo
    from ..item import Item
    from ..interceptors import ChainManager, InterruptibleChainManager
    from ..spiders import Spider
    from .sessions import SessionManager, SessionWrapper, WebSocketEntry

class Engine:
    def __init__(self, crawler: "Crawler", spider: "Spider"):
        self.stop_event: asyncio.Event = crawler.stop_event
        self.taskManager: "TaskManager" = crawler.taskManager
        self.settings: "SettingsInfo" = crawler.settings

        self.sessions: "SessionManager" = crawler.sessions
        self.sessions_lock: asyncio.Lock = crawler.sessions_lock

        self.signalManager: "SignalManager" = crawler.signalManager
        self.scheduler: "Scheduler" = crawler.scheduler
        self.downloader: "Downloader" = crawler.downloader
        self.spider: "Spider" = spider
        self.spiderInterceptor_chain: "InterruptibleChainManager" = crawler.spiderInterceptor_chain
        self.downloadInterceptor_chain: "InterruptibleChainManager" = crawler.downloadInterceptor_chain
        self.pipelines_chain: "ChainManager" = crawler.pipelines_chain

        from ..utils import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)

    @classmethod
    def from_crawler(cls, crawler: "Crawler", spider: "Spider"):
        return cls(
            crawler=crawler,
            spider=spider,
        )

    async def start(self, *args, **kwargs):
        self.signalManager.send(signal=signals.engine_started, data=SingalInfo(signal_time=time.time()))
        await self.pipelines_chain.forward_pass(call_func_cls=self.pipelines_chain.chain_list[0].instance, call_func_name="open_spider", pad_data=self.spider)
        self.signalManager.send(signal=signals.spider_opened, data=SingalInfo(spider=self.spider, signal_time=time.time()))

        # Retrieve requests directly from the spider's start method without additional processing,
        # mark them as start URLs, and submit them to the spider middleware chain.
        async for output in self.spider.start(*args, **kwargs):
            await self.taskManager.create(coro=self.get_spider_output(output=output, mark_as_start=True))
        try:
            await self.taskManager.wait_until_stopped()
        except KeyboardInterrupt as e:
            async with self.taskManager.lock:
                self.taskManager.active_tasks -= 1

        await self.pipelines_chain.forward_pass(call_func_cls=self.pipelines_chain.chain_list[0].instance, call_func_name="close_spider", pad_data=self.spider)
        await self.signalManager._safe_put(signal=signals.spider_closed, data=SingalInfo(spider=self.spider, signal_time=time.time()))
        await self.signalManager._safe_put(signal=signals.engine_stopped, data=SingalInfo(signal_time=time.time()))

    async def get_spider_output(self, output, response=None, mark_as_start=False):
        async for single_result in _ensure_asyncgen(output):
            if isinstance(single_result, Request) and mark_as_start:
                single_result.meta["is_start_url"] = True
            async for item in self.spiderInterceptor_chain.process_spider_output_chain(
                response=response,
                result=single_result,
                spider=self.spider
            ):
                await self.taskManager.create(coro=self.manager_spiderinterceptors_result(spiderinterceptors_result=item))

    async def manager_spiderinterceptors_result(self, spiderinterceptors_result: ChainResult):
        if spiderinterceptors_result.next == ChainNextEnum.RESCHEDULE:
            await self.taskManager.create(coro=self.process_scheduler(request=spiderinterceptors_result.request))
        elif spiderinterceptors_result.next == ChainNextEnum.SPIDER:
            await self.process_response(response=spiderinterceptors_result.response, request=spiderinterceptors_result.request)
        elif spiderinterceptors_result.next == ChainNextEnum.PIPELINE:
            await self.process_items(item=spiderinterceptors_result.item)
        elif spiderinterceptors_result.next == ChainNextEnum.EXCEPTION:
            if not spiderinterceptors_result.is_across:
                await self.spiderInterceptor_chain.process_spider_exception_chain(
                    response=spiderinterceptors_result.response, 
                    exception=spiderinterceptors_result.exception, 
                    spider=spiderinterceptors_result.spider, 
                    callback=self.manager_spiderinterceptors_result,
                    is_across=1
                )
            else:
                data = spiderinterceptors_result.model_dump().copy()
                data.pop("next", None)
                data.pop("is_across", None)
                data["signal_time"] = time.time()
                self.signalManager.send(signal=signals.spider_error, data=SingalInfo(**data))

    # Scheduler: repeatedly fetches and processes requests until none are left.
    async def process_scheduler(self, request: Request=None):
        if request:
            put_scheduler = await self.scheduler.put(request=request, spider=self.spider)
            if put_scheduler:
                await self.taskManager.create(coro=self.process_scheduler())
            else:
                return

        if self.scheduler.is_distributed:
            request = await self.scheduler.get(spider=self.spider)
            if isinstance(request, int) and not request: # scheduler empty
                self.signalManager.send(signal=signals.scheduler_empty, data=SingalInfo(signal_time=time.time()))
                return
            elif isinstance(request, Request):
                await self.taskManager.create(coro=self.process_downloadInterceptor_chain(request=request))
        else:
            try:
                request = await asyncio.wait_for(self.scheduler.get(spider=self.spider), timeout=1.0)
                await self.taskManager.create(coro=self.process_downloadInterceptor_chain(request=request))
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                raise
            if self.scheduler.empty(spider=self.spider):
                self.signalManager.send(signal=signals.scheduler_empty, data=SingalInfo(signal_time=time.time()))
                return 
            else:
                await self.taskManager.create(coro=self.process_scheduler())

    # Download middleware processing
    async def process_downloadInterceptor_chain(self, response: Union[Response, BaseException, None]=None, request: Request=None):
        if response:
            await self.downloadInterceptor_chain.response_intercept_chain(request=request, response=response, spider=self.spider, callback=self.manager_downloadinterceptors_result)
        elif request:
            await self.downloadInterceptor_chain.request_intercept_chain(request=request, spider=self.spider, callback=self.manager_downloadinterceptors_result)
    
    # Handles results from the download interceptors or exceptions raised during downloading.
    async def manager_downloadinterceptors_result(self, downloadinterceptors_result: ChainResult):
        if downloadinterceptors_result.next == ChainNextEnum.RESCHEDULE:
            await self.taskManager.create(coro=self.process_scheduler(request=downloadinterceptors_result.request))
        elif downloadinterceptors_result.next == ChainNextEnum.SPIDER:
            await self.spiderInterceptor_chain.process_spider_input_chain(
                response=downloadinterceptors_result.response, 
                request=downloadinterceptors_result.request, 
                spider=self.spider, 
                callback=self.manager_spiderinterceptors_result
            )
        elif downloadinterceptors_result.next == ChainNextEnum.DOWNLOADER:
            await self.taskManager.create(coro=self.process_downloader(request=downloadinterceptors_result.request))
        elif downloadinterceptors_result.next == ChainNextEnum.EXCEPTION:
            if not downloadinterceptors_result.is_across:
                await self.downloadInterceptor_chain.exception_intercept_chain(request=downloadinterceptors_result.request, exception=downloadinterceptors_result.exception, spider=downloadinterceptors_result.spider, callback=self.manager_downloadinterceptors_result, is_across=1)
            else:
                await self.process_response(response=downloadinterceptors_result.exception, request=downloadinterceptors_result.request)

    # Downloader
    async def process_downloader(self, request: Request):
        if isinstance(request, HttpRequest):
            await self.downloader.fetch_http(request=request, callback=self.process_downloadInterceptor_chain)
        elif isinstance(request, WebSocketRequest):
            await self.taskManager.create(coro=self.process_websocket_request(request=request))
            
    # Callback to spider with the response
    async def process_response(self, response: Union[Response, BaseException], request: Request):
        if isinstance(response, BaseException):
            output = self.get_backFunc(backFunc=request.errback, response=response, fill_text=f"Response error {str(response)} with no errback provided, ignoring this request")
            if not output:
                return
        elif isinstance(response, Response):
            await self.scheduler.put_is_req(request=request, spider=self.spider)
            output = self.get_backFunc(backFunc=request.callback, response=response)
        else:
            return
        await self.taskManager.create(coro=self.get_spider_output(output=output, response=response))

    # manager callback
    def get_backFunc(self, backFunc=None, response: Union[Response, BaseException]=None, fill_text=""):
        if isinstance(backFunc, str):
            callbackFunc = getattr(self.spider, backFunc, None)
        elif callable(backFunc):
            callbackFunc = backFunc
        else:
            callbackFunc = None
            
        if callbackFunc:
            output = callbackFunc(response) if response else callbackFunc()
            return output
        else:
            if isinstance(response, HttpResponse):
                self.logger.info(f"Response succeeded with text: {response.text}, no callback provided, task finished.")
            elif isinstance(response, WebSocketResponse):
                self.logger.info(f"Response succeeded with message: {response.msg[0]}, no callback provided, task finished.")
            else:
                self.logger.info(fill_text)

    async def process_items(self, item: Union["Item", Dict]):
        self.signalManager.send(signal=signals.item_scraped, data=SingalInfo(signal_time=time.time(), item=item, spider=self.spider))
        await self.pipelines_chain.forward_pass(call_func_cls=self.pipelines_chain.chain_list[0].instance, call_func_name="process_item", pad_data=item, spider=self.spider)

    # Process a WebSocket request
    async def process_websocket_request(self, request: WebSocketRequest):
        wrapper: "SessionWrapper" = self.sessions.get_or_create_session(request.session_id, cookies=request.cookies)
        if not request.url:
            raise ValueError("Scheduling logic error: this request was not properly processed by spider middleware")
        
        websocket_entry: "WebSocketEntry" = wrapper.get_websocket(request.url)
        if websocket_entry:
            if request.websocket_end and request.url:
                wrapper.websocket_pool.mark_end_from_url(url=request.url)
                websocket_entry.release()
                self.sessions.release(request.session_id)
                return
            if request.send_message:
                if getattr(getattr(websocket_entry.websocket, "curl", None), "_curl", None) is not None:
                    # WebSocket communication is deduplicated by connection only.
                    # Once connection uniqueness is ensured, subsequent messages run on a single device,
                    # so message deduplication is handled only by new_req_seen, not in is_req.
                    # Send the message asynchronously in a thread to avoid blocking.

                    # await run_with_timeout(ws.send, request.send_message, stop_event=self.stop_event, timeout=3)
                    for msg in request.send_message:
                        if asyncio.iscoroutinefunction(websocket_entry.websocket.send):
                            await websocket_entry.websocket.send(msg)
                        else:
                            await asyncio.to_thread(websocket_entry.websocket.send, msg)
                websocket_entry.release()
                self.sessions.release(request.session_id)
            return
        await self.do_websocket_connect(wrapper=wrapper, connect_request=request)

    async def do_websocket_connect(self, wrapper: "SessionWrapper", connect_request: WebSocketRequest):
        try:
            task, queue, websocket_event = await self.downloader.fetch_websocket(wrapper, connect_request)
            while (not self.stop_event.is_set()) and (not websocket_event.is_set()):
                msg = await queue.get()
                if isinstance(msg, DownloadError) or (isinstance(msg, str) and msg == self.settings.WS_END_TAG):
                    websocket_event.set()
                    # task.cancel()
                    # self.logger.debug(f'{msg}: {connect_request.url}, listener ended')
                    break
                await self.taskManager.create(coro=self.process_downloadInterceptor_chain(response=msg, request=connect_request))
                if b'keepalive ping timeout' in msg.msg[0]:
                    websocket_event.set()
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            self.logger.debug(f'WebSocket listener task cancelled: {connect_request.url}')
            raise
        except BaseException as e:
            results = DownloadError(exception=e, request=connect_request)
            await self.taskManager.create(coro=self.process_downloadInterceptor_chain(response=results, request=connect_request))
            connect_request.websocket_end = True
            await self.process_websocket_request(request=connect_request)
        finally:
            # Release session regardless of normal exit or exception cancellation
            self.sessions.release(connect_request.session_id) # Release the session
            await wrapper.close_websocket(connect_request.url) # Close underlying connection