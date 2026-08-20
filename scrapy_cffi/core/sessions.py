# Key Notes:
# Single-threaded asyncio design: All operations are expected to run within the same event loop to avoid concurrency problems.
# Reference counting: Ensures sessions are not closed while still in use.
# Group sessions: Supports grouping multiple session IDs under one logical group for random selection and batch closing.
# WebSocket management: Each session can maintain multiple WebSocket connections, managed individually.
# Safe async cleanup: Uses a background task (_reaper_loop) to close sessions when no longer needed.

import asyncio, hashlib, random
from functools import partial
from http.cookiejar import Cookie
from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed, retry_if_exception_type
from typing import Union, Dict, Set, TYPE_CHECKING, Literal, Optional, List
from .client_hints import ClientHintsState
from .downloader.internet import MediaRequest
from ..platform.http import (
    AsyncHttpSessionProtocol,
    AsyncHttpStreamProtocol,
    AsyncWebSocketProtocol,
    HttpResponseProtocol,
    HttpSessionFactory,
    HttpTransportError,
)
from ..utils.algorithm import create_uniqueId
from ..utils.common import run_with_timeout
from ..utils.concurrency import safe_call
from ..utils.state_codec import decode_state, encode_state
if TYPE_CHECKING:
    from logging import Logger
    from ..crawler import Crawler
    from ..settings import SettingsInfo
    from .downloader.internet import HttpRequest, WebSocketRequest
    from ..repo.queue import KafkaQueueRepository
    from ..models.api import WebSocketMsg

_INHERIT_SESSION_RATE = object()

class CloseSignal:
    def __init__(
        self, 
        session_id: str, 
        websocket_end_for_key: Union[str, Literal[False], None]=False, 
        websocket_end_for_url: Union[str, Literal[False], None]=False, 
        session_end=False
    ):
        self.session_id = session_id
        self.websocket_end_for_key = websocket_end_for_key
        self.websocket_end_for_url = websocket_end_for_url
        self.session_end = session_end

    def __repr__(self):
        return f"<CloseSignal session_id={self.session_id} ws_end={self.websocket_end_for_url} sess_end={self.session_end}>"


class _LoopNeutralEvent:
    """Expose the Event subset used here without binding during construction."""

    def __init__(self) -> None:
        self._is_set = False
        self._event: Optional[asyncio.Event] = None

    def is_set(self) -> bool:
        """Return whether the event has been set."""
        return self._is_set

    def set(self) -> None:
        """Set the flag and wake waiters after an event loop has been bound."""
        self._is_set = True
        if self._event is not None:
            self._event.set()

    async def wait(self) -> bool:
        """Bind an asyncio event only while running inside its owning loop."""
        if self._is_set:
            return True
        if self._event is None:
            self._event = asyncio.Event()
        await self._event.wait()
        return True


class WebSocketEntry:
    """Own one WebSocket connection and its event-driven listener lifecycle."""

    def __init__(
        self,
        logger,
        url: str,
        ping_data: "WebSocketMsg" = None,
        ping_interval: float = 15.0,
    ) -> None:
        """Create a registered connection before its listener task starts."""
        self.logger: "Logger" = logger
        self.url: str = url
        self.task: Optional[asyncio.Task] = None
        self.websocket: Optional[AsyncWebSocketProtocol] = None
        # Python 3.9 binds asyncio.Event to the current loop in __init__.
        # Entries may be registered synchronously, so defer loop binding until
        # the first asynchronous wait while retaining synchronous set/is_set.
        self.stop_event = _LoopNeutralEvent()
        self.closed_event = _LoopNeutralEvent()
        self._ping_data = ping_data
        self._ping_interval = ping_interval

        self.ref_count = 0
        self.marked_end = False
        self._closed = False
        self._close_lock: Optional[asyncio.Lock] = None
        self._ping_task: Optional[asyncio.Task] = None

    def set_listener_task(self, task: asyncio.Task) -> None:
        """Attach the retained listener task after pool registration."""
        self.task = task

    def set_websocket(self, websocket: AsyncWebSocketProtocol) -> None:
        """Attach the connected socket and start optional protocol pings."""
        self.websocket = websocket
        if self._ping_data is not None and self._ping_task is None:
            self._ping_task = asyncio.create_task(
                self._ping_loop(self._ping_data, self._ping_interval)
            )

    def acquire(self) -> None:
        """Retain one callback or follow-up request reference."""
        self.ref_count += 1

    def release(self) -> None:
        """Release one reference and request stop after an explicit end."""
        self.ref_count -= 1
        if self.marked_end and self.ref_count <= 0:
            self.request_stop()

    def request_stop(self) -> None:
        """Request listener shutdown without sending a queue sentinel."""
        self.marked_end = True
        self.stop_event.set()

    def mark_end(self) -> None:
        """Keep the legacy CloseSignal entrypoint on the event-driven path."""
        self.marked_end = True
        if self.ref_count <= 0:
            self.request_stop()

    async def wait_closed(self) -> None:
        """Wait until the listener owner completes connection cleanup."""
        await self.closed_event.wait()

    async def _ping_loop(
        self,
        ping_data: "WebSocketMsg",
        interval: float,
    ) -> None:
        """Send optional application pings until stop is requested."""
        try:
            while not self.stop_event.is_set():
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=interval)
                    break
                except asyncio.TimeoutError:
                    pass
                try:
                    if self.websocket:
                        await safe_call(
                            self.websocket.send,
                            ping_data.data,
                            flags=ping_data.flags,
                        )
                except Exception as e:
                    self.logger.warning(f"[WebSocketEntry] Ping failed for {self.url}: {e}")
                    self.request_stop()
                    break
        except asyncio.CancelledError:
            raise

    async def close(self) -> None:
        """Close listener, ping task, and socket exactly once."""
        current_task = asyncio.current_task()
        if self._close_lock is None:
            self._close_lock = asyncio.Lock()
        try:
            async with self._close_lock:
                if self._closed:
                    return
                self._closed = True
                self.stop_event.set()
                ping_task = self._ping_task
                listener_task = self.task
                websocket = self.websocket

            if ping_task and ping_task is not current_task:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass

            if listener_task and listener_task is not current_task:
                listener_task.cancel()
                try:
                    await listener_task
                except asyncio.CancelledError:
                    self.logger.debug(f"[WebSocketEntry] Listener task cancelled for {self.url}")
                except Exception as e:
                    self.logger.warning(f"[WebSocketEntry] Listener task raised exception for {self.url}: {e}")

            if websocket is not None:
                try:
                    await websocket.close()
                except Exception as e:
                    self.logger.warning(f"[WebSocketEntry] websocket.close() error for {self.url}: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.error(f"[WebSocketEntry] Error closing websocket for {self.url}: {e}")
        finally:
            self.closed_event.set()

class WebSocketPool:
    """Own event-driven WebSocket entries under one HTTP session."""

    def __init__(self, logger=None) -> None:
        """Create an empty connection pool."""
        self._pool: Dict[str, WebSocketEntry] = {}
        self.logger: "Logger" = logger

    def _key(self, url: str) -> str:
        """Build the stable connection key used by public responses."""
        return hashlib.md5(url.encode("utf-8")).hexdigest()

    def init_websocket(
        self,
        url: str,
        ping_data: "WebSocketMsg" = None,
        ping_interval: float = 15.0,
    ) -> WebSocketEntry:
        """Register an entry before creating its listener task."""
        key = self._key(url)
        if key not in self._pool:
            self._pool[key] = WebSocketEntry(
                logger=self.logger,
                url=url,
                ping_data=ping_data,
                ping_interval=ping_interval,
            )
        return self._pool[key]

    def set_listener_task(self, url: str, task: asyncio.Task) -> None:
        """Attach the listener task to an already registered entry."""
        entry = self.get_from_url(url)
        if entry is None:
            raise ValueError("WebSocketEntry has not been initialized yet.")
        entry.set_listener_task(task)
    
    def set_websocket(self, url: str, websocket: AsyncWebSocketProtocol) -> str: # return websocket_id
        """Attach one connected socket and return its public identifier."""
        key = self._key(url)
        if key not in self._pool:
            raise ValueError("WebSocketEntry has not been initialized yet.")
        self._pool[key].set_websocket(websocket)
        return key
    
    def get_from_key(self, key: str) -> Optional[WebSocketEntry]:
        return self._pool.get(key)

    def get_from_url(self, url: str) -> Optional[WebSocketEntry]:
        key = self._key(url)
        return self.get_from_key(key)
    
    def acquire_from_key(self, key: str):
        websocket_entry = self.get_from_key(key)
        if websocket_entry:
            websocket_entry.acquire()

    def acquire_from_url(self, url: str):
        websocket_entry = self.get_from_url(url)
        if websocket_entry:
            websocket_entry.acquire()

    def release_from_key(self, key: str):
        websocket_entry = self.get_from_key(key)
        if websocket_entry:
            websocket_entry.release()

    def release_from_url(self, url: str):
        websocket_entry = self.get_from_url(url)
        if websocket_entry:
            websocket_entry.release()

    def mark_end_from_key(self, key: str):
        websocket_entry = self.get_from_key(key)
        if websocket_entry:
            websocket_entry.mark_end()

    def mark_end_from_url(self, url: str):
        websocket_entry = self.get_from_url(url)
        if websocket_entry:
            websocket_entry.mark_end()

    def remove(self, key: str) -> Optional[WebSocketEntry]:
        """Remove one entry by public identifier."""
        entry = self._pool.pop(key, None)
        return entry

    def remove_from_url(self, url: str) -> Optional[WebSocketEntry]:
        """Remove one entry by connection URL."""
        return self.remove(self._key(url))

    async def close_all(self) -> None:
        """Close and remove every connection owned by the session."""
        for entry in list(self._pool.values()):
            await entry.close()
        self._pool.clear()


class SessionRequestLimiter:
    """Space request attempts for one concrete in-memory HTTP session."""

    def __init__(self, requests_per_second: Optional[float] = None) -> None:
        """Create an unlimited or fixed-rate session admission policy."""
        self._lock = asyncio.Lock()
        self._next_start = 0.0
        self.configure(requests_per_second)

    def configure(self, requests_per_second: Optional[float]) -> None:
        """Replace the rate used by future request admissions."""
        if requests_per_second is not None and requests_per_second <= 0:
            raise ValueError("requests_per_second must be greater than zero")
        self.requests_per_second = requests_per_second
        self._interval = (
            0.0
            if requests_per_second is None
            else 1.0 / float(requests_per_second)
        )

    async def wait(self) -> None:
        """Wait until the next configured start time for this session."""
        if self._interval <= 0:
            return
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            delay = self._next_start - now
            if delay > 0:
                await asyncio.sleep(delay)
                now = loop.time()
            self._next_start = max(now, self._next_start) + self._interval


class SessionWrapper:
    """
    Represents a single HTTP/WS session identified by a session ID.
    Wraps a framework HTTP session and maintains a WebSocketPool for that session.
    Supports configuring session-level cookies, retry policy, performing HTTP and WebSocket requests with retries, and closing connections.
    """
    def __init__(
        self,
        stop_event: asyncio.Event,
        settings: "SettingsInfo" = None,
        cookies: Dict = None,
        kafka_repository: "KafkaQueueRepository" = None,
        http_session_factory: HttpSessionFactory = None,
        requests_per_second: Optional[float] = None,
    ):
        self.stop_event = stop_event
        self.settings = settings
        from ..utils.log import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)
        if kafka_repository:
            from ..utils.log import KafkaLoggingHandler
            kafka_handler = KafkaLoggingHandler(kafka=kafka_repository, stop_event=self.stop_event).create_fmt(self.settings)
            self.logger.addHandler(kafka_handler)

        if http_session_factory is None:
            from ..platform.curl_cffi import CurlCffiHttpSession

            http_session_factory = partial(CurlCffiHttpSession)
        self.session: AsyncHttpSessionProtocol = http_session_factory()
        from ..profiles import get_impersonate_resolver

        self._impersonate_resolver = get_impersonate_resolver()
        self.client_hints = ClientHintsState()
        self.websocket_pool: WebSocketPool = WebSocketPool(logger=self.logger)
        self.request_limiter = SessionRequestLimiter(requests_per_second)
        self.default_cookies = cookies or self.settings.DEFAULT_COOKIES
        self.update_session_cookies(self.default_cookies)
        self._lock = asyncio.Lock()

    def _request_retryer(
        self,
        request: Union["HttpRequest", "WebSocketRequest"],
    ) -> AsyncRetrying:
        """Build the retry policy selected by one request or global settings."""
        retry_times = request.max_retry_times or self.settings.MAX_REQ_TIMES
        retry_delay = (
            request.retry_delay
            if request.retry_delay is not None
            else self.settings.DELAY_REQ_TIME
        )
        return AsyncRetrying(
            stop=stop_after_attempt(retry_times),
            wait=wait_fixed(retry_delay),
            retry=retry_if_exception_type((HttpTransportError, ConnectionError, TimeoutError, OSError)),
            reraise=True
        )

    def _build_request_args(self, request: "HttpRequest") -> Dict:
        args = {
            "url": request.url,
            "headers": request.headers,
            "cookies": request.cookies,
            "proxies": request.proxies,
            "timeout": request.timeout,
            "allow_redirects": request.allow_redirects,
            "max_redirects": request.max_redirects,
            "verify": request.verify,
            "impersonate": self._impersonate_resolver(request.impersonate),
            "ja3": request.ja3,
            "akamai": request.akamai,
        }
        if request.data:
            args["data"] = request.data
        args.update({k: v for k, v in request.kwargs.items() if k != "json"})
        return args
    
    async def do_request(self, request: Union["HttpRequest", "WebSocketRequest"], is_ws: bool = False):
        async for attempt in self._request_retryer(request):
            with attempt:
                if is_ws:
                    return await self.ws_connect_once(request)
                else:
                    return await self.do_request_once(request)
                
    async def media_req(self, request: MediaRequest):
        all_file_data = []
        part_byte_start = 0
        part_byte_end = request.single_part_size
        single_part_response = None
        while not self.stop_event.is_set():
            if request.media_size < part_byte_end: # The size of the last segment = total file size - the starting index of the next segment to obtain the file bytes
                part_byte_end = request.media_size - part_byte_start
            else:
                part_byte_end = part_byte_start + request.single_part_size
            
            range_key = request.find_header_key("Range")
            range_key = range_key if range_key else "Range"
            request.headers[range_key] = f"bytes={part_byte_start}-{part_byte_end}"
            await self.request_limiter.wait()
            single_part_response: HttpResponseProtocol = await self.session.request(
                method=request.method, 
                **self._build_request_args(request)
            )
            single_part_data = single_part_response.content
            all_file_data.append(single_part_data)
            part_byte_start = part_byte_end + 1
            if part_byte_start >= request.media_size:
                media_data = b''.join(all_file_data)
                single_part_response.content = media_data
                break
        return single_part_response
    
    async def do_request_once(self, request: "HttpRequest"):
        if isinstance(request, MediaRequest):
            return await self.media_req(request=request)

        await self.request_limiter.wait()
        method: Literal["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH"] = request.method
        raw_response = await self.session.request(
            method=method,
            **self._build_request_args(request)
        )
        return raw_response

    async def open_stream(self, request: "HttpRequest") -> AsyncHttpStreamProtocol:
        """Open a live HTTP stream through the configured platform session."""
        async for attempt in self._request_retryer(request):
            with attempt:
                await self.request_limiter.wait()
                return await self.session.open_stream(
                    method=request.method,
                    **self._build_request_args(request),
                )
        raise RuntimeError("HTTP stream retry policy completed without a result")
    
    async def ws_connect_once(self, request: "WebSocketRequest") -> AsyncWebSocketProtocol:
        await self.request_limiter.wait()
        websocket = await self.session.connect_websocket(url=request.url,
            headers=request.headers, 
            cookies=self.session.cookies.get_dict(),
            proxies=request.proxies, 
            timeout=request.timeout,
            allow_redirects=request.allow_redirects,
            max_redirects=request.max_redirects,
            verify=request.verify,
            impersonate=self._impersonate_resolver(request.impersonate),
            ja3=request.ja3,
            akamai=request.akamai,
            **request.kwargs
        )
        # Automatic pinging is built-in, but curl_cffi lacks `ping_data` config,
        # so manual protocol-level ping frames cannot be sent.
        return websocket
    
    def get_websocket(self, url: str) -> WebSocketEntry:
        return self.websocket_pool.get_from_url(url)
    
    def init_websocket(
        self,
        url: str,
        ping_data: "WebSocketMsg" = None,
        ping_interval: float = 15.0,
    ) -> WebSocketEntry:
        """Register a WebSocket entry before its listener starts."""
        return self.websocket_pool.init_websocket(
            url=url,
            ping_data=ping_data,
            ping_interval=ping_interval,
        )

    def set_websocket_listener(self, url: str, task: asyncio.Task) -> None:
        """Attach the retained listener task to one registered connection."""
        self.websocket_pool.set_listener_task(url=url, task=task)

    def set_websocket(self, url: str, websocket: AsyncWebSocketProtocol) -> str: # return websocket_id
        return self.websocket_pool.set_websocket(url=url, websocket=websocket)

    def update_session_cookies(self, cookies_dict: Dict):
        for ck, val in cookies_dict.items():
            self.session.cookies.set(ck, val)

    def export_cookies(self) -> List[Dict]:
        """Return the complete cookie jar as JSON-safe records."""
        return [
            {
                "version": cookie.version,
                "name": cookie.name,
                "value": cookie.value,
                "port": cookie.port,
                "port_specified": cookie.port_specified,
                "domain": cookie.domain,
                "domain_specified": cookie.domain_specified,
                "domain_initial_dot": cookie.domain_initial_dot,
                "path": cookie.path,
                "path_specified": cookie.path_specified,
                "secure": cookie.secure,
                "expires": cookie.expires,
                "discard": cookie.discard,
                "comment": cookie.comment,
                "comment_url": cookie.comment_url,
                "rest": getattr(cookie, "_rest", {}),
                "rfc2109": cookie.rfc2109,
            }
            for cookie in self.session.cookies.jar
        ]

    def import_cookies(self, cookies: List[Dict], replace: bool = True) -> None:
        """Restore cookie records without losing domain/path/expiry metadata."""
        if replace:
            self.session.cookies.clear()
        for data in cookies:
            self.session.cookies.jar.set_cookie(Cookie(**data))

    async def session_close(self):
        await self.session.close()

    async def close_websocket(self, identifier: str) -> None:
        """Close and remove a WebSocket by identifier or URL."""
        entry = self.websocket_pool.get_from_key(identifier)
        if entry is None:
            entry = self.websocket_pool.get_from_url(identifier)
        if entry:
            await entry.close()
            self.websocket_pool.remove_from_url(entry.url)

class SessionManager:
    """
    The central manager for all sessions running within a single-threaded asyncio event loop.
    Maintains a mapping from session IDs to SessionWrapper instances and groups of session IDs.
    Tracks reference counts for each session to manage usage, marks sessions as ended when tasks complete, and queues sessions for safe asynchronous cleanup via a background reaper loop.
    Provides methods to get/create sessions, batch register sessions with cookies, acquire/release sessions references, mark sessions as ended, and close sessions/groups safely without concurrency issues.
    """
    def __init__(self, stop_event=None, settings=None, kafka_repository=None, http_session_factory: HttpSessionFactory = None):
        self._default_session_id = create_uniqueId()
        self._sessions: Dict[str, SessionWrapper] = {self._default_session_id: None}
        self._group_sessions: Dict[str, List[str]] = {}

        self.stop_event: asyncio.Event = stop_event
        self.settings: "SettingsInfo" = settings
        self.kafka_repository: "KafkaQueueRepository" = kafka_repository
        self.http_session_factory = http_session_factory

        # Tracks the current reference count (usage) for each session_id. Format: {session_id: count}
        self._ref_counts: Dict[str, int] = {} 

        # Marks session_ids whose tasks have completed and are eligible for release.
        # Uses a set to ensure idempotency, added via user calls to mark_end.
        self._end_flags: set[str] = set() 
        
        # Queue of session_ids that have met the conditions for closure,
        # to be processed asynchronously by the background _reaper_loop coroutine.
        self._close_queue: asyncio.Queue = asyncio.Queue()

        # A deduplication set to prevent the same session_id from being added multiple times to the close queue.
        self._pending_close_set: Set[str] = set()
        self._restored_session_fields: Set[tuple[str, str]] = set()
        self._session_rates: Dict[str, Optional[float]] = {}
        self._frozen = False
        from ..utils.log import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)
        if self.kafka_repository:
            from ..utils.log import KafkaLoggingHandler
            kafka_handler = KafkaLoggingHandler(kafka=self.kafka_repository, stop_event=self.stop_event).create_fmt(self.settings)
            self.logger.addHandler(kafka_handler)

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event, 
            settings=crawler.settings,
            kafka_repository=crawler.resources.kafka,
            http_session_factory=crawler.http_session_factory,
        )

    def debug_sessions(self):
        self.logger.debug(f"[SessionManager] Current sessions: {list(self._sessions.keys())}")
        self.logger.debug(f"[SessionManager] Reference counts: {self._ref_counts}")
        self.logger.debug(f"[SessionManager] End flags: {self._end_flags}")
        self.logger.debug(f"[SessionManager] Pending close queue: {list(self._pending_close_set)}")
            
    def start(self):
        if not hasattr(self, "_reaper_task") or self._reaper_task.done():
            self._reaper_task = asyncio.create_task(self._reaper_loop())

    def get_or_create_session(self, session_id: str, cookies: Dict=None) -> SessionWrapper:
        if not session_id:
            session_id = self._default_session_id

        if session_id in self._group_sessions:
            actual_session_ids = self._group_sessions[session_id]
            if not actual_session_ids:
                raise ValueError(f"[SessionManager] Group session '{session_id}' has no valid session members.")
            session_id = random.choice(actual_session_ids)

        wrapper = self._sessions.get(session_id)
        if wrapper:
            if cookies:
                wrapper.update_session_cookies(cookies)
            return wrapper

        wrapper = SessionWrapper(
            stop_event=self.stop_event,
            settings=self.settings,
            cookies=cookies,
            kafka_repository=self.kafka_repository,
            http_session_factory=self.http_session_factory,
            requests_per_second=self._session_rates.get(
                session_id,
                self.settings.SESSION_REQUESTS_PER_SECOND,
            ),
        )
        self._sessions[session_id] = wrapper
        return wrapper
    
    def register_sessions_batch(
        self,
        user_cookies: Dict[str, Dict],
        group_id: Optional[str] = None,
        requests_per_second=_INHERIT_SESSION_RATE,
    ) -> str:
        """Register a group; omitted rate inherits settings and ``None`` is unlimited."""
        if not user_cookies:
            return

        group_id = group_id or create_uniqueId()
        session_ids = []
        selected_rate = (
            self.settings.SESSION_REQUESTS_PER_SECOND
            if requests_per_second is _INHERIT_SESSION_RATE
            else requests_per_second
        )
        if selected_rate is not None and selected_rate <= 0:
            raise ValueError("requests_per_second must be greater than zero")

        for session_id, cookies in user_cookies.items():
            if session_id not in self._sessions:
                wrapper = SessionWrapper(
                    stop_event=self.stop_event,
                    settings=self.settings,
                    cookies=cookies,
                    kafka_repository=self.kafka_repository,
                    http_session_factory=self.http_session_factory,
                    requests_per_second=selected_rate,
                )
                self._sessions[session_id] = wrapper
                self._session_rates[session_id] = selected_rate
                session_ids.append(session_id)
            else:
                self.logger.info(f"[SessionManager] Session {session_id} already exists, skipped.")

        self._group_sessions[group_id] = session_ids
        self.logger.debug(f"[SessionManager] Registered group '{group_id}' with sessions: {session_ids}")
        return group_id

    def configure_rate_limit(
        self,
        session_id: str,
        requests_per_second: Optional[float],
    ) -> None:
        """Configure one session or every member of an existing session group."""
        if requests_per_second is not None and requests_per_second <= 0:
            raise ValueError("requests_per_second must be greater than zero")
        if session_id in self._group_sessions:
            targets = list(self._group_sessions[session_id])
        else:
            targets = [session_id or self._default_session_id]
        for target in targets:
            self._session_rates[target] = requests_per_second
            wrapper = self._sessions.get(target)
            if wrapper is not None:
                wrapper.request_limiter.configure(requests_per_second)
    
    async def close_group_sessions(self, group_id: str):
        session_ids = self._group_sessions.pop(group_id, [])
        for session_id in session_ids:
            self.mark_end(session_id)

    def freeze(self):
        self._frozen = True
    
    def is_default_session(self, session_id: str) -> bool:
        return session_id == self._default_session_id

    def acquire(self, session_id: str):
        # self.debug_sessions()
        if self.is_default_session(session_id) or not session_id:
            return
        self._ref_counts[session_id] = self._ref_counts.get(session_id, 0) + 1
        # self.debug_sessions()

    def release(self, session_id: str):
        # self.debug_sessions()
        if self.is_default_session(session_id) or not session_id:
            return
        if session_id not in self._ref_counts:
            self.logger.warning(f"[SessionManager] Release called on unacquired session_id: {session_id}")
            return
        self._ref_counts[session_id] -= 1

        if (session_id in self._end_flags) and (self._ref_counts[session_id] <= 0) and (session_id not in self._pending_close_set):
            self._close_queue.put_nowait(session_id)
            self._pending_close_set.add(session_id)
        # self.debug_sessions()

    def mark_end_single(self, session_id):
        self._end_flags.add(session_id)
        
        ref_count = self._ref_counts.get(session_id, 0)
        if ref_count <= 0 and (session_id not in self._pending_close_set):
            self._close_queue.put_nowait(session_id)
            self._pending_close_set.add(session_id)

    def mark_end(self, session_id: str):
        if self.is_default_session(session_id) or (not session_id):
            return
        
        if session_id in self._group_sessions:
            for it in self._group_sessions[session_id]:
                self.mark_end_single(it)
        else:
            _group_session = self._group_sessions.copy()
            for it in self._group_sessions:
                if session_id in self._group_sessions[it]:
                    _group_session[it].remove(session_id)
                    break
            self._group_sessions = _group_session
            self.mark_end_single(session_id)

    async def _reaper_loop(self):
        try:
            while not self.stop_event.is_set():
                session_id = await run_with_timeout(self._close_queue.get, stop_event=self.stop_event, timeout=0.5)
                try:
                    await self._safe_close(session_id)
                except Exception as e:
                    self.logger.error(f"[SessionManager] Error closing session {session_id}: {e}")
                finally:
                    self._pending_close_set.discard(session_id)
                    self._close_queue.task_done()
            raise asyncio.CancelledError()
        except asyncio.CancelledError:
            raise

    async def _safe_close(self, session_id: str):
        if self._frozen:
            return
        if self.is_default_session(session_id) or (not session_id):
            return
        wrapper = self._sessions.pop(session_id, None)
        if wrapper:
            self.logger.debug(f"[SessionManager] Closing session: {session_id}")
            await wrapper.websocket_pool.close_all()
            await wrapper.session_close()

    def get_session_cookies(self, session_id: str) -> Union[Dict, None]:
        ret_cookies = {}
        if session_id in self._group_sessions:
            session_ids = self._group_sessions[session_id]
            for it in session_ids:
                wrapper = self._sessions.get(it)
                if wrapper:
                    ret_cookies[it] = wrapper.session.cookies.get_dict()
        else:
            wrapper = self._sessions.get(session_id)
            if wrapper:
                ret_cookies = {session_id: wrapper.session.cookies.get_dict()}
        return ret_cookies

    @staticmethod
    def _state_field(session_id: str) -> str:
        return "D" if not session_id else f"S:{session_id}"

    async def persist_session(self, redis_manager, state_key: str, session_id: str) -> bool:
        """Persist one logical session into a Redis Hash field."""
        field = self._state_field(session_id)
        if session_id in self._group_sessions:
            members = {}
            for member_id in self._group_sessions[session_id]:
                wrapper = self._sessions.get(member_id)
                if wrapper:
                    members[member_id] = {
                        "cookies": wrapper.export_cookies(),
                        "client_hints": wrapper.client_hints.export_state(),
                    }
            state = {"kind": "group", "members": members}
        else:
            actual_id = session_id or self._default_session_id
            wrapper = self._sessions.get(actual_id)
            if not wrapper:
                return False
            state = {
                "kind": "session",
                "cookies": wrapper.export_cookies(),
                "client_hints": wrapper.client_hints.export_state(),
            }

        await redis_manager.hset(state_key, field, encode_state(state))
        self._restored_session_fields.add((state_key, field))
        return True

    async def persist_all(self, redis_manager, state_key: str) -> int:
        """Snapshot all live sessions, used for a graceful persistent shutdown."""
        logical_ids = set(self._sessions)
        logical_ids.discard(self._default_session_id)
        logical_ids.update(self._group_sessions)
        logical_ids.add("")
        persisted = 0
        for session_id in logical_ids:
            persisted += int(await self.persist_session(redis_manager, state_key, session_id))
        return persisted

    async def restore_session(self, redis_manager, state_key: str, session_id: str) -> bool:
        """Lazily restore only the session referenced by a dequeued request."""
        field = self._state_field(session_id)
        marker = (state_key, field)
        if marker in self._restored_session_fields:
            return False
        payload = await redis_manager.hget(state_key, field)
        self._restored_session_fields.add(marker)
        if payload is None:
            return False

        state = decode_state(payload)
        if state["kind"] == "group":
            member_ids = []
            for member_id, member_state in state["members"].items():
                wrapper = self.get_or_create_session(member_id)
                if isinstance(member_state, dict):
                    cookies = member_state.get("cookies", [])
                    client_hints = member_state.get("client_hints")
                else:
                    cookies = member_state
                    client_hints = None
                wrapper.import_cookies(cookies)
                wrapper.client_hints.import_state(client_hints)
                member_ids.append(member_id)
            self._group_sessions[session_id] = member_ids
        else:
            wrapper = self.get_or_create_session(session_id)
            wrapper.import_cookies(state["cookies"])
            wrapper.client_hints.import_state(state.get("client_hints"))
        return True

    async def close_all(self) -> None:
        reaper_task = getattr(self, "_reaper_task", None)
        if reaper_task and not reaper_task.done():
            reaper_task.cancel()
            try:
                await reaper_task
            except asyncio.CancelledError:
                pass
        self._frozen = False
        await asyncio.gather(*[self._safe_close(session_id) for session_id in list(self._sessions.keys())])
        self._sessions.clear()
        self._ref_counts.clear()
        self._end_flags.clear()
        self._pending_close_set.clear()
        self._session_rates.clear()
        while not self._close_queue.empty():
            self._close_queue.get_nowait()
            self._close_queue.task_done()
