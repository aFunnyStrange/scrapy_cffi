import asyncio, time
from ..extensions import signals, SignalInfo
from .downloader import *
from ..exceptions import DownloadError, SessionEndError
from ..interceptors import ChainResult, ChainNextEnum
from ..interceptors.chains import _ensure_asyncgen
from ..utils.concurrency import safe_call, CallFunction
from typing import TYPE_CHECKING, Dict, Union
if TYPE_CHECKING:
    from ..crawler import Crawler
    from .tasks import TaskManager
    from .scheduler import Scheduler
    from ..extensions import SignalManager
    from ..settings import SettingsInfo
    from ..item import Item
    from ..interceptors import ChainManager, InterruptibleChainManager
    from ..spiders import Spider
    from .sessions import SessionManager, SessionWrapper, WebSocketEntry, CloseSignal

class Engine:
    _WORK_ID_META_KEY = "_scrapy_cffi_engine_work_id"

    def __init__(self, crawler: "Crawler", spider: "Spider", scheduler: "Scheduler"):
        self.stop_event: asyncio.Event = crawler.stop_event
        self.taskManager: "TaskManager" = crawler.taskManager
        self.settings: "SettingsInfo" = crawler.settings

        self.sessions: "SessionManager" = crawler.sessions
        self.sessions_lock: asyncio.Lock = crawler.sessions_lock

        self.signalManager: "SignalManager" = crawler.signalManager
        self.scheduler: "Scheduler" = scheduler
        self.downloader: "Downloader" = crawler.downloader
        self.spider: "Spider" = spider
        self.spiderInterceptor_chain: "InterruptibleChainManager" = crawler.spiderInterceptor_chain
        self.downloadInterceptor_chain: "InterruptibleChainManager" = crawler.downloadInterceptor_chain
        self.pipelines_chain: "ChainManager" = crawler.pipelines_chain

        base_req_limit = self.settings.MAX_CONCURRENT_REQ
        self.max_inflight_downloader_tasks = (
            None
            if base_req_limit is None
            else max(int(base_req_limit) * 2, 50)
        )
        self._work_sequence = 0
        self._pending_work_ids = set()
        self._work_idle_event = asyncio.Event()
        self._work_idle_event.set()

        # Select the hot scheduling path once. The loop no longer branches on
        # scheduler.is_distributed for every dequeued request.
        if self.scheduler.is_distributed:
            self.scheduler_loop = self._distributed_scheduler_loop
        else:
            self.scheduler_loop = self._local_scheduler_loop

        from ..utils.log import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)
        if crawler.resources.kafka:
            from ..utils.log import KafkaLoggingHandler
            kafka_handler = KafkaLoggingHandler(kafka=crawler.resources.kafka, stop_event=self.stop_event).create_fmt(self.settings)
            self.logger.addHandler(kafka_handler)

    @classmethod
    def from_crawler(cls, crawler: "Crawler", spider: "Spider", scheduler: "Scheduler"):
        return cls(crawler=crawler, spider=spider, scheduler=scheduler)

    async def start(self, *args, **kwargs):
        self.signalManager.send(signal=signals.engine_started, data=SignalInfo(signal_time=time.time()))
        if self.pipelines_chain.chain_list: # In fact, at least one pipeline component must be registered, otherwise there may be bugs
            await self.pipelines_chain.forward_pass(call_func_cls=self.pipelines_chain.chain_list[0].instance, call_func_name="open_spider", pad_data=self.spider)
        self.signalManager.send(signal=signals.spider_opened, data=SignalInfo(spider=self.spider, signal_time=time.time()))

        # Retrieve requests directly from the spider's start method without additional processing,
        # mark them as start URLs, and submit them to the spider middleware chain.
        producer_task = await self.taskManager.create(
            callfunc=CallFunction(
                func=self.run_spider_start,
                args=args,
                kwargs=kwargs,
            )
        )

        # Start a centralized scheduler loop:
        # Unlike the old recursive process_scheduler (where each put/get would create a new task forming a deep task chain),
        # the centralized scheduler_loop runs as a single persistent task, avoiding the overhead of excessive coroutine switching
        # caused by a growing task tree, significantly improving throughput and scheduling stability.
        # Recursive mode may give a more immediate "task chaining" perception to the user,
        # but it severely reduces performance under high concurrency.
        scheduler_tasks = []
        for _ in range(self.settings.MAX_SCHEDULER_LOOP_NUM):
            scheduler_tasks.append(
                await self.taskManager.create(
                    callfunc=CallFunction(func=self.scheduler_loop)
                )
            )

        scheduler_group = asyncio.gather(*scheduler_tasks)
        error_wait = asyncio.create_task(self.taskManager.error_event.wait())
        completion_wait = asyncio.create_task(
            self._wait_for_explicit_completion(producer_task)
        )
        try:
            done, _ = await asyncio.wait(
                (scheduler_group, error_wait, completion_wait),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if error_wait in done:
                for scheduler_task in scheduler_tasks:
                    scheduler_task.cancel()
                await asyncio.gather(*scheduler_tasks, return_exceptions=True)
            elif completion_wait in done:
                await completion_wait
                for scheduler_task in scheduler_tasks:
                    scheduler_task.cancel()
                await asyncio.gather(*scheduler_tasks, return_exceptions=True)
            else:
                await scheduler_group
        except KeyboardInterrupt:
            pass
        finally:
            if not error_wait.done():
                error_wait.cancel()
            if not completion_wait.done():
                completion_wait.cancel()
            if not scheduler_group.done():
                for scheduler_task in scheduler_tasks:
                    scheduler_task.cancel()
            await asyncio.gather(
                error_wait,
                completion_wait,
                scheduler_group,
                return_exceptions=True,
            )
            if producer_task is not None and not producer_task.done():
                producer_task.cancel()
            if producer_task is not None:
                await asyncio.gather(producer_task, return_exceptions=True)
            await self.taskManager.wait_for_object_idle(id(self))

        if self.pipelines_chain.chain_list:
            await self.pipelines_chain.forward_pass(call_func_cls=self.pipelines_chain.chain_list[0].instance, call_func_name="close_spider", pad_data=self.spider)
        await self.signalManager._safe_put(signal=signals.spider_closed, data=SignalInfo(spider=self.spider, signal_time=time.time()))
        await self.signalManager._safe_put(signal=signals.engine_stopped, data=SignalInfo(signal_time=time.time()))

    async def run_spider_start(self, *args, **kwargs):
        async for output in self.spider.start(*args, **kwargs):
            await self.taskManager.create(
                callfunc=CallFunction(func=self.get_spider_output, output=output, mark_as_start=True)
            )

    def _ensure_work_state(self) -> None:
        """Initialize request ownership for tests constructing Engine directly."""
        if not hasattr(self, "_pending_work_ids"):
            self._work_sequence = 0
            self._pending_work_ids = set()
            self._work_idle_event = asyncio.Event()
            self._work_idle_event.set()

    def _track_request(self, request: Request) -> None:
        """Own one accepted request until its complete callback boundary."""
        self._ensure_work_state()
        work_id = request.meta.get(self._WORK_ID_META_KEY)
        if not work_id:
            self._work_sequence += 1
            work_id = f"{id(self)}:{self._work_sequence}"
            request.meta[self._WORK_ID_META_KEY] = work_id
        if work_id not in self._pending_work_ids:
            self._pending_work_ids.add(work_id)
            self._work_idle_event.clear()

    def _release_request(self, request: Request) -> None:
        """Publish a real idle event after one owned request completes."""
        self._ensure_work_state()
        work_id = request.meta.get(self._WORK_ID_META_KEY)
        if work_id:
            self._pending_work_ids.discard(work_id)
        if not self._pending_work_ids:
            self._work_idle_event.set()

    async def _complete_request(self, request: Request) -> None:
        """Complete broker acknowledgement before releasing Engine ownership."""
        complete = getattr(getattr(self, "scheduler", None), "complete_request", None)
        if complete:
            await complete(request, getattr(self, "spider", None))
        self._release_request(request)

    async def _wait_for_explicit_completion(
        self,
        producer_task: asyncio.Task,
    ) -> None:
        """Finish only after producer completion and request ownership reaches zero."""
        self._ensure_work_state()
        await producer_task
        while True:
            await self._work_idle_event.wait()
            await self.taskManager.wait_for_object_quiescent(
                id(self),
                exclude_prefixes=(
                    "_local_scheduler_loop",
                    "_distributed_scheduler_loop",
                    "run_spider_start",
                ),
            )
            if self._work_idle_event.is_set():
                self.signalManager.send(
                    signal=signals.scheduler_empty,
                    data=SignalInfo(signal_time=time.time()),
                )
                return

    async def _wait_for_downloader_capacity(self) -> None:
        """Suspend until a downloader task completion publishes capacity."""
        if self.max_inflight_downloader_tasks is None:
            return
        await self.taskManager.wait_for_object_task_count_below(
            id(self),
            prefixes=("process_downloader",),
            limit=self.max_inflight_downloader_tasks,
        )

    async def _distributed_scheduler_loop(self):
        try:
            while not self.stop_event.is_set():
                await self._wait_for_downloader_capacity()
                request = await self.scheduler.get(spider=self.spider)
                if isinstance(request, int) and (not request): # scheduler empty
                    continue
                elif isinstance(request, Request):
                    await self.taskManager.create(callfunc=CallFunction(func=self.process_downloadInterceptor_chain, request=request))
        except asyncio.CancelledError:
            raise

    async def _local_scheduler_loop(self):
        try:
            while not self.stop_event.is_set():
                await self._wait_for_downloader_capacity()
                request = await self.scheduler.get(spider=self.spider)
                if isinstance(request, Request):
                    await self.taskManager.create(callfunc=CallFunction(func=self.process_downloadInterceptor_chain, request=request))
        except asyncio.CancelledError:
            raise

    async def get_spider_output(self, output, response=None, mark_as_start=False, source_request=None):
        completed = False
        try:
            async for single_result in _ensure_asyncgen(output):
                if isinstance(single_result, Request) and mark_as_start:
                    single_result.meta["is_start_url"] = True
                async for item in self.spiderInterceptor_chain.process_spider_output_chain(
                    response=response,
                    result=single_result,
                    spider=self.spider
                ):
                    if source_request is not None:
                        # Broker acknowledgement must happen after every child
                        # request/item has actually crossed its next boundary.
                        await self.manager_spiderinterceptors_result(item, wait_for_boundary=True)
                    else:
                        await self.taskManager.create(callfunc=CallFunction(func=self.manager_spiderinterceptors_result, spiderinterceptors_result=item))
            completed = True
        finally:
            if isinstance(response, StreamResponse):
                await response.aclose()
            if (
                completed
                and source_request is not None
                and not isinstance(response, WebSocketResponse)
            ):
                await self._complete_request(source_request)

    async def manager_spiderinterceptors_result(self, spiderinterceptors_result: ChainResult, wait_for_boundary=False):
        if spiderinterceptors_result.next == ChainNextEnum.RESCHEDULE:
            if wait_for_boundary:
                await self.enqueue_request(request=spiderinterceptors_result.request)
            else:
                await self.taskManager.create(callfunc=CallFunction(func=self.enqueue_request, request=spiderinterceptors_result.request))
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
                data["signal_time"] = time.time()
                self.signalManager.send(signal=signals.spider_error, data=SignalInfo(**data))
        elif spiderinterceptors_result.next == ChainNextEnum.SESSION:
            if spiderinterceptors_result.signal.websocket_end_for_key or spiderinterceptors_result.signal.websocket_end_for_url:
                self.end_websocket(signal=spiderinterceptors_result.signal)
            elif spiderinterceptors_result.signal.session_end:
                self.sessions.mark_end(session_id=spiderinterceptors_result.signal.session_id)
                self.sessions.release(
                    session_id=spiderinterceptors_result.signal.session_id
                )

    def end_websocket(self, signal: "CloseSignal"):
        wrapper: "SessionWrapper" = self.sessions.get_or_create_session(signal.session_id)
        if signal.websocket_end_for_url:
            websocket_entry: "WebSocketEntry" = wrapper.websocket_pool.get_from_url(signal.websocket_end_for_url)
            if not websocket_entry:
                return
            end_url = websocket_entry.url
        elif signal.websocket_end_for_key: # In fact, the spiderInterceptor already has a key ->URL
            websocket_entry: "WebSocketEntry" = wrapper.websocket_pool.get_from_key(signal.websocket_end_for_key)
            if not websocket_entry:
                return
            end_url = websocket_entry.url
        else:
            return
        wrapper.websocket_pool.mark_end_from_url(end_url)
        websocket_entry.release()
        self.sessions.release(signal.session_id)

    async def enqueue_request(self, request: Request=None):
        if self.stop_event.is_set():
            return
            
        if request:
            self._track_request(request)
            try:
                accepted = await self.scheduler.put(
                    request=request,
                    spider=self.spider,
                )
            except BaseException:
                self._release_request(request)
                raise
            if accepted is False:
                self._release_request(request)

    # Download middleware processing
    async def process_downloadInterceptor_chain(self, response: Union[Response, BaseException, None]=None, request: Request=None):
        if response:
            await self.downloadInterceptor_chain.response_intercept_chain(request=request, response=response, spider=self.spider, callback=self.manager_downloadinterceptors_result)
        elif request:
            await self.downloadInterceptor_chain.request_intercept_chain(request=request, spider=self.spider, callback=self.manager_downloadinterceptors_result)
    
    # Handles results from the download interceptors or exceptions raised during downloading.
    async def manager_downloadinterceptors_result(self, downloadinterceptors_result: ChainResult):
        if downloadinterceptors_result.next == ChainNextEnum.RESCHEDULE:
            await self.taskManager.create(callfunc=CallFunction(func=self.enqueue_request, request=downloadinterceptors_result.request))
        elif downloadinterceptors_result.next == ChainNextEnum.DOWNLOADER:
            await self.taskManager.create(callfunc=CallFunction(func=self.process_downloader, request=downloadinterceptors_result.request))
        elif downloadinterceptors_result.next == ChainNextEnum.RESPONSE:
            await self.taskManager.create(callfunc=CallFunction(func=self.process_downloadInterceptor_chain, response=downloadinterceptors_result.response, request=downloadinterceptors_result.request))
        elif downloadinterceptors_result.next == ChainNextEnum.SPIDER:
            await self.spiderInterceptor_chain.process_spider_input_chain(
                response=downloadinterceptors_result.response, 
                request=downloadinterceptors_result.request, 
                spider=self.spider, 
                callback=self.manager_spiderinterceptors_result
            )
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
            await self.taskManager.create(callfunc=CallFunction(func=self.process_websocket_request, request=request))
            
    # Callback to spider with the response
    async def process_response(self, response: Union[Response, BaseException], request: Request):
        if isinstance(response, BaseException):
            output = self.get_backFunc(backFunc=request.errback, response=response, fill_text=f"Response error {str(response)} with no errback provided, ignoring this request")
            if not output:
                await self._complete_request(request)
                return
        elif isinstance(response, Response):
            await self.scheduler.put_is_req(request=request, spider=self.spider)
            output = self.get_backFunc(backFunc=request.callback, response=response)
        else:
            return
        if not self.stop_event.is_set():
            await self.taskManager.create(callfunc=CallFunction(func=self.get_spider_output, output=output, response=response, source_request=request))

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
        self.signalManager.send(signal=signals.item_scraped, data=SignalInfo(signal_time=time.time(), item=item, spider=self.spider))
        await self.pipelines_chain.forward_pass(call_func_cls=self.pipelines_chain.chain_list[0].instance, call_func_name="process_item", pad_data=item, spider=self.spider)

    # Process a WebSocket request
    async def process_websocket_request(self, request: WebSocketRequest):
        wrapper: "SessionWrapper" = self.sessions.get_or_create_session(request.session_id, cookies=request.cookies)
        if not request.url:
            raise ValueError("Scheduling logic error: this request was not properly processed by spider middleware")

        # A request carrying websocket_id is a send on an existing connection,
        # even when the spider interceptor resolved its URL earlier. The
        # listener may close between enqueue and download; never reinterpret
        # that stale send as a new long-lived connection.
        if request.websocket_id:
            websocket_entry: "WebSocketEntry" = (
                wrapper.websocket_pool.get_from_key(request.websocket_id)
            )
            if websocket_entry is None or websocket_entry.websocket is None:
                self.sessions.release(request.session_id)
                await self.process_downloadInterceptor_chain(
                    response=SessionEndError(
                        exception=ValueError(
                            f"WebSocket connection {request.websocket_id} has closed"
                        ),
                        request=request,
                    ),
                    request=request,
                )
                return
        else:
            websocket_entry = wrapper.get_websocket(request.url)
        if websocket_entry and request.send_message:
            if websocket_entry.websocket is not None:
                # WebSocket communication is deduplicated by connection only.
                # Once connection uniqueness is ensured, subsequent messages run on a single device,
                # so message deduplication is handled only by new_req_seen, not in is_req.
                for msg in request.send_message:
                    await websocket_entry.websocket.send(msg.data, flags=msg.flags)

            websocket_entry.release()
            self.sessions.release(request.session_id)
            await self._complete_request(request)
            return
        await self.do_websocket_connect(wrapper=wrapper, connect_request=request)

    async def do_websocket_connect(self, wrapper: "SessionWrapper", connect_request: WebSocketRequest):
        terminal = False
        try:
            entry = await self.downloader.fetch_websocket(
                wrapper,
                connect_request,
                callback=self.process_downloadInterceptor_chain,
            )
            await entry.wait_closed()
            terminal = True
        except asyncio.CancelledError:
            self.logger.debug(f'WebSocket listener task cancelled: {connect_request.url}')
            raise
        except Exception as e:
            results = DownloadError(exception=e, request=connect_request)
            await self.taskManager.create(callfunc=CallFunction(func=self.process_downloadInterceptor_chain, response=results, request=connect_request))
            self.end_websocket(signal=CloseSignal(session_id=connect_request.session_id, websocket_end_for_url=connect_request.url))
            terminal = True
        finally:
            # Release session regardless of normal exit or exception cancellation
            self.sessions.release(connect_request.session_id) # Release the session
            await wrapper.close_websocket(connect_request.url) # Close underlying connection
            if terminal:
                await self._complete_request(connect_request)
