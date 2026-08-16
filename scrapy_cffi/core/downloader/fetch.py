import asyncio, time
from ...utils import async_context_factory, safe_call, run_with_timeout
from typing import TYPE_CHECKING, List, Callable
# from ...utils import run_with_timeout
from .internet import *
from ...exceptions import DownloadError
from ...extensions import signals, SignalInfo
if TYPE_CHECKING:
    from ...crawler import Crawler
    from ...settings import SettingsInfo
    from ...extensions import SignalManager
    from ..sessions import SessionManager, SessionWrapper, WebSocketEntry
    from ...repo.queue import KafkaQueueRepository

class Downloader:
    def __init__(
        self, 
        stop_event: asyncio.Event=None, 
        settings: "SettingsInfo"=None, 
        sessions: "SessionManager"=None, 
        sessions_lock=None, 
        signalManager: "SignalManager"=None,
        kafka_repository: "KafkaQueueRepository"=None
    ):
        self.stop_event = stop_event
        self.settings = settings
        from ...utils import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)
        if kafka_repository:
            from ...utils import KafkaLoggingHandler
            kafka_handler = KafkaLoggingHandler(kafka=kafka_repository, stop_event=self.stop_event).create_fmt(self.settings)
            self.logger.addHandler(kafka_handler)

        self.sessions = sessions
        self.sessions_lock = sessions_lock
        self.signalManager = signalManager
        # Set the maximum concurrency limit for requests
        self.sem_ctx = async_context_factory(
            max_tasks=self.settings.MAX_CONCURRENT_REQ,
            semaphore_cls=asyncio.Semaphore if not self.settings.USE_STRICT_SEMAPHORE else None
        )
        stream_limit = self.settings.MAX_CONCURRENT_REQ or 100
        self._stream_semaphore = asyncio.Semaphore(stream_limit)
        self._websocket_semaphore = asyncio.Semaphore(stream_limit)

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            settings=crawler.settings,
            sessions=crawler.sessions,
            sessions_lock=crawler.sessions_lock,
            signalManager=crawler.signalManager,
            kafka_repository=crawler.resources.kafka,
        )
    
    async def fetch_http(self, request: HttpRequest, callback: Callable) -> asyncio.Task:
        try:
            self.signalManager.send(signal=signals.request_reached_downloader, data=SignalInfo(signal_time=time.time(), request=request))
            wrapper: "SessionWrapper" = self.sessions.get_or_create_session(
                session_id=request.session_id,
                cookies=request.cookies
            )
            if request.stream:
                await self._fetch_stream(wrapper=wrapper, request=request, callback=callback)
                return
            raw_response = None
            async with self.sem_ctx():
                # Some curl_cffi calls can occasionally hang on cancellation under heavy load.
                # Enforce a hard upper bound here so process_downloader cannot stall indefinitely.
                hard_timeout = max(float(request.timeout or self.settings.TIMEOUT or 30), 1.0) + 2.0
                raw_response = await run_with_timeout(
                    wrapper.do_request,
                    request=request,
                    stop_event=self.stop_event,
                    timeout=hard_timeout,
                    max_total_time=hard_timeout,
                )

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
                self.signalManager.send(signal=signals.response_received, data=SignalInfo(signal_time=time.time(), request=request, response=response))
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

    async def _fetch_stream(
        self,
        wrapper: "SessionWrapper",
        request: HttpRequest,
        callback: Callable,
    ) -> None:
        """Open a bounded live stream and transfer closure to StreamResponse."""
        await self._stream_semaphore.acquire()
        response = None
        try:
            hard_timeout = max(float(request.timeout or self.settings.TIMEOUT or 30), 1.0) + 2.0
            stream = await run_with_timeout(
                wrapper.open_stream,
                request=request,
                stop_event=self.stop_event,
                timeout=hard_timeout,
                max_total_time=hard_timeout,
            )
            response = StreamResponse(
                stream=stream,
                release=self._stream_semaphore.release,
                session_id=request.session_id,
                meta=request.meta,
                dont_filter=request.dont_filter,
                callback=request.callback,
                errback=request.errback,
                desc_text=request.desc_text,
                request=request,
            )
            self.signalManager.send(
                signal=signals.response_received,
                data=SignalInfo(signal_time=time.time(), request=request, response=response),
            )
            await callback(response=response, request=request)
        except BaseException:
            if response is not None:
                await response.aclose()
            else:
                self._stream_semaphore.release()
            raise

    async def cancel_ws_tasks(self, tasks: List[asyncio.Task]):
        for t in tasks:
            if not t.done():
                t.cancel()
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.logger.debug(f"Downloader Task cancelled or failed: {e}")

    async def _websocket_listener(
        self,
        entry: "WebSocketEntry",
        wrapper: "SessionWrapper",
        request: WebSocketRequest,
        callback: Callable,
    ) -> None:
        """Dispatch socket messages directly until an event requests stop."""
        try:
            async with self._websocket_semaphore:
                websocket = await wrapper.do_request(request=request, is_ws=True)
                websocket_id = wrapper.set_websocket(url=request.url, websocket=websocket)
                if entry.stop_event.is_set() or self.stop_event.is_set():
                    return
                if request.send_message:
                    # Preserve connect-and-send as one operation for servers
                    # that close idle handshakes almost immediately.
                    for msg in request.send_message:
                        await safe_call(websocket.send, msg.data, flags=msg.flags)

                while not self.stop_event.is_set() and not entry.stop_event.is_set():
                    tasks = []
                    try:
                        recv_task = asyncio.create_task(websocket.recv())
                        wait_task = asyncio.create_task(entry.stop_event.wait())
                        stop_task = asyncio.create_task(self.stop_event.wait())
                        tasks = [recv_task, wait_task, stop_task]
                        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        await self.cancel_ws_tasks(tasks=list(pending))
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
                                request=request,
                                stop_listening=entry.request_stop,
                            )
                            self.signalManager.send(signal=signals.response_received, data=SignalInfo(signal_time=time.time(), request=request, response=response))
                            await callback(response=response, request=request)
                            if (
                                isinstance(msg, (tuple, list))
                                and msg
                                and isinstance(msg[0], bytes)
                                and b"keepalive ping timeout" in msg[0]
                            ):
                                entry.request_stop()
                        else:
                            break
                    except asyncio.CancelledError:
                        await self.cancel_ws_tasks(tasks=tasks)
                        raise
                    except Exception as e:
                        result = DownloadError(exception=e, request=request)
                        self.logger.error(str(result))
                        await callback(response=result, request=request)
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
                await callback(response=result, request=request)
            except Exception as callback_error:
                self.logger.warning(
                    f"WebSocket error callback failed for {request.url}: "
                    f"{callback_error}"
                )
        finally:
            await entry.close()

    async def fetch_websocket(
        self,
        wrapper: "SessionWrapper",
        request: WebSocketRequest,
        callback: Callable,
    ) -> "WebSocketEntry":
        """Register and start one event-driven WebSocket listener."""
        self.signalManager.send(
            signal=signals.request_reached_downloader,
            data=SignalInfo(signal_time=time.time(), request=request),
        )
        entry = wrapper.init_websocket(
            url=request.url,
            ping_data=request.ping_data,
            ping_interval=request.ping_interval,
        )
        task = asyncio.create_task(
            self._websocket_listener(
                entry=entry,
                wrapper=wrapper,
                request=request,
                callback=callback,
            )
        )
        wrapper.set_websocket_listener(url=request.url, task=task)
        return entry
