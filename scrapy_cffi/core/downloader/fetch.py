import asyncio, time
from contextlib import asynccontextmanager
from typing import Tuple, TYPE_CHECKING, List, Callable
# from ...utils import run_with_timeout
from .internet import *
from ...exceptions import DownloadError
from ...extensions import signals
from ...models.api import SingalInfo
if TYPE_CHECKING:
    from ...crawler import Crawler
    from ...models.api import SettingsInfo
    from ...extensions import SignalManager
    from ..sessions import SessionManager, SessionWrapper

class Downloader:
    def __init__(self, stop_event: asyncio.Event=None, settings: "SettingsInfo"=None, sessions: "SessionManager"=None, sessions_lock=None, signalManager: "SignalManager"=None):
        self.stop_event = stop_event
        self.settings = settings
        from ...utils import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)
        self.sessions = sessions
        self.sessions_lock = sessions_lock
        self.signalManager = signalManager
        # Set the maximum concurrency limit for requests
        if self.settings.MAX_CONCURRENT_REQ is None:
            self.sem_ctx = self.dummy_async_context
        else:
            semaphore_cls = asyncio.BoundedSemaphore if self.settings.USE_STRICT_SEMAPHORE else asyncio.Semaphore
            sem = semaphore_cls(self.settings.MAX_CONCURRENT_REQ)
            @asynccontextmanager
            async def sem_context():
                async with sem:
                    yield
            self.sem_ctx = sem_context

    @staticmethod
    @asynccontextmanager
    async def dummy_async_context():
        yield

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            settings=crawler.settings,
            sessions=crawler.sessions,
            sessions_lock=crawler.sessions_lock,
            signalManager=crawler.signalManager,
        )
    
    async def fetch_http(self, request: HttpRequest, callback: Callable) -> asyncio.Task:
        try:
            self.signalManager.send(signal=signals.request_reached_downloader, data=SingalInfo(signal_time=time.time(), request=request))
            wrapper: "SessionWrapper" = self.sessions.get_or_create_session(
                session_id=request.session_id,
                cookies=request.cookies
            )
            raw_response = None
            async with self.sem_ctx():
                raw_response = await wrapper.do_request(session=wrapper.session, request=request)

            if raw_response:
                response = HttpResponse(
                    session_id=request.session_id,
                    raw_response=raw_response,
                    meta=request.meta,
                    dont_filter=request.dont_filter,
                    callback=request.callback,
                    errback=request.errback,
                    desc_text=request.desc_text,
                    request=request
                )
                self.logger.debug(f'request for {request.url} result -> status_code: {response.status_code}')
                self.signalManager.send(signal=signals.response_received, data=SingalInfo(signal_time=time.time(), request=request, response=response))
                await callback(response=response, request=request)
            else:
                self.logger.warning(f'HTTP request timed out or got no response: {request.url}')
        except asyncio.CancelledError as e:
            raise
        except Exception as e:
            result = DownloadError(request=request, exception=e)
            self.logger.error(str(result))
            await callback(response=result, request=request)
        finally:
            async with self.sessions_lock:
                self.sessions.release(session_id=request.session_id)

    async def cancel_ws_tasks(self, tasks: List[asyncio.Task]):
        for t in tasks:
            if not t.done():
                t.cancel()
        for t in tasks:
            try:
                await t
            except Exception as e:
                self.logger.debug(f"Downloader Task cancelled or failed: {e}")

    async def downloaderWebSocketListener(self, websocket_event: asyncio.Event, wrapper: "SessionWrapper", request: WebSocketRequest, queue: asyncio.Queue):
        try:
            async with self.sem_ctx():
                websocket = await wrapper.do_request(session=wrapper.session, request=request, is_ws=True)
                websocket_id = wrapper.set_websocket(url=request.url, websocket=websocket)
                if request.send_message: # Sending requests is supported during the initial WebSocket handshake
                    # await run_with_timeout(websocket.send, request.send_message, stop_event=self.stop_event)
                    for msg in request.send_message:
                        if asyncio.iscoroutinefunction(websocket.send):
                            await websocket.send(msg)
                        else:
                            await asyncio.to_thread(websocket.send, msg)

                while (not self.stop_event.is_set()) and (not websocket_event.is_set()):
                    try:
                        if asyncio.iscoroutinefunction(websocket.recv):
                            recv_task = asyncio.create_task(websocket.recv())
                        else:
                            recv_task = asyncio.create_task(asyncio.to_thread(websocket.recv))
                        wait_task = asyncio.create_task(websocket_event.wait())
                        stop_task = asyncio.create_task(self.stop_event.wait())
                        tasks = [recv_task, wait_task, stop_task]
                        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        if recv_task in done:
                            msg = recv_task.result()
                            # if msg[0] in [b'\x03\xe8', b'\x03\xe8Bye', b'\x03\xf3keepalive ping timeout']: # Predefined termination messages as per protocol convention
                            #     break
                            
                            response = WebSocketResponse(
                                session_id=request.session_id,
                                websocket_id=websocket_id,
                                msg=msg,
                                meta=request.meta,
                                callback=request.callback,
                                errback=request.errback,
                                desc_text=request.desc_text,
                                request=request
                            )
                            self.signalManager.send(signal=signals.response_received, data=SingalInfo(signal_time=time.time(), request=request, response=response))
                            await queue.put(response)
                        else:
                            await self.cancel_ws_tasks(tasks=tasks)
                            break
                    except asyncio.CancelledError:
                        await self.cancel_ws_tasks(tasks=tasks)
                        raise
                    except Exception as e:
                        result = DownloadError(exception=e, request=request)
                        self.logger.error(str(result))
                        await queue.put(result)
                        # if "initializer for ctype" in str(e):
                        #     self.logger.info(f"WebSocket connection {request.url} has already been closed. Exiting listener.")
                        break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # self.logger.error(f"DownloadError：{e}")
            result = DownloadError(exception=e, request=request)
            self.logger.error(str(result))
            try:
                await queue.put(result)
            except Exception as e:
                self.logger.warning(f"fetch Queue put failed: {e}")
        finally:
            websocket_event.set()
            await queue.put(self.settings.WS_END_TAG)

    async def fetch_websocket(self, wrapper: "SessionWrapper", request: WebSocketRequest) -> Tuple[asyncio.Task, asyncio.Queue, asyncio.Event]:
        self.signalManager.send(signal=signals.request_reached_downloader, data=SingalInfo(signal_time=time.time(), request=request))
        websocket_event = asyncio.Event()
        websocket_event.clear()
        queue = asyncio.Queue()
        task = asyncio.create_task(self.downloaderWebSocketListener(websocket_event=websocket_event, wrapper=wrapper, request=request, queue=queue))
        websocket_id = wrapper.init_websocket(url=request.url, task=task, queue=queue)
        return task, queue, websocket_event