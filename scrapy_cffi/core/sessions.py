# Key Notes:
# Single-threaded asyncio design: All operations are expected to run within the same event loop to avoid concurrency problems.
# Reference counting: Ensures sessions are not closed while still in use.
# Group sessions: Supports grouping multiple session IDs under one logical group for random selection and batch closing.
# WebSocket management: Each session can maintain multiple WebSocket connections, managed individually.
# Safe async cleanup: Uses a background task (_reaper_loop) to close sessions when no longer needed.

import asyncio, hashlib, random
from curl_cffi import requests
from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed, retry_if_exception_type
from typing import Union, Dict, Set, TYPE_CHECKING, Literal, Optional, List
from .downloader.internet import MediaRequest
from ..utils import create_uniqueId, run_with_timeout
if TYPE_CHECKING:
    from logging import Logger
    from ..crawler import Crawler
    from ..models.api import SettingsInfo
    from curl_cffi.requests import Response
    from .downloader.internet import HttpRequest, WebSocketRequest

class WebSocketEntry:
    """
    Represents a single WebSocket connection identified by its URL (including parameters) and the underlying WebSocket object.
    Manages reference counting for shared usage, supports graceful close on last release or explicit end marking, and handles listener task cancellation and connection cleanup.
    """
    def __init__(self, logger, end_tag, url, task, queue):
        self.logger: "Logger" = logger
        self.end_tag: str = end_tag
        self.url: str = url
        self.task: asyncio.Task = task
        self.websocket: requests.websockets.WebSocket = None
        self.queue: asyncio.Queue = queue
        self.stop_event: asyncio.Event = asyncio.Event()
        self.stop_event.clear()

        self.ref_count = 0
        self.marked_end = False
        self._closed = False
        self._close_lock = asyncio.Lock()

    def acquire(self):
        self.ref_count += 1

    def release(self):
        self.ref_count -= 1
        if self.marked_end and self.ref_count <= 0:
            asyncio.create_task(self.close())

    def mark_end(self):
        self.marked_end = True
        if self.ref_count <= 0:
            asyncio.create_task(self.close())

    async def close(self):
        try:
            async with self._close_lock:
                if self._closed:
                    return
                self._closed = True

                self.stop_event.set()
                await self.queue.put(self.end_tag)

                if self.task:
                    self.task.cancel()
                    try:
                        await self.task
                    except asyncio.CancelledError:
                        self.logger.debug(f"[WebSocketEntry] Listener task cancelled for {self.url}")
                    except Exception as e:
                        self.logger.warning(f"[WebSocketEntry] Listener task raised exception for {self.url}: {e}")

                ws_curl = getattr(getattr(self.websocket, "curl", None), "_curl", None)
                if ws_curl is None:
                    self.logger.debug(f"[WebSocketEntry] websocket already released for {self.url}")
                    return

                if hasattr(self.websocket, "close"):
                    try:
                        if asyncio.iscoroutinefunction(self.websocket.close):
                            await self.websocket.close()
                        else:
                            self.websocket.close()
                    except Exception as e:
                        self.logger.warning(f"[WebSocketEntry] websocket.close() error for {self.url}: {e}")
        except BaseException as e:
            self.logger.error(f"[WebSocketEntry] Error closing websocket for {self.url}: {e}")

class WebSocketPool:
    """
    Manages all WebSocket connections under a single session.
    Keeps a dictionary of WebSocketEntry objects keyed by the MD5 hash of their URL.
    Supports initialization, acquisition, release, marking end, retrieval, and cleanup of WebSocket connections.
    """
    def __init__(self, logger=None):
        self._pool: Dict[str, WebSocketEntry] = {}
        self.logger: "Logger" = logger

    def _key(self, url: str) -> str:
        return hashlib.md5(url.encode("utf-8")).hexdigest()

    def init_websocket(self, end_tag: str, url: str, task: asyncio.Task, queue: asyncio.Queue) -> str: # return websocket_id
        key = self._key(url)
        if key not in self._pool:
            self._pool[key] = WebSocketEntry(logger=self.logger, end_tag=end_tag, url=url, task=task, queue=queue)
        return key
    
    def set_websocket(self, url: str, websocket: requests.websockets.WebSocket) -> str: # return websocket_id
        key = self._key(url)
        if key not in self._pool:
            raise ValueError(f'WebSocketEntry has not been initialized yet.')
        self._pool[key].websocket = websocket
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
        entry = self._pool.pop(key, None)
        return entry

    async def close_all(self):
        for entry in list(self._pool.values()):
            await entry.close()
        self._pool.clear()

class SessionWrapper:
    """
    Represents a single HTTP/WS session identified by a session ID.
    Wraps an asynchronous HTTP session (curl_cffi.requests.AsyncSession) and maintains a WebSocketPool for that session.
    Supports configuring session-level cookies, retry policy, performing HTTP and WebSocket requests with retries, and closing connections.
    """
    def __init__(self, stop_event: asyncio.Event, settings: "SettingsInfo"=None, cookies: Dict=None):
        self.stop_event = stop_event
        self.settings = settings
        from ..utils import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)

        self.session = requests.AsyncSession()
        self.websocket_pool: WebSocketPool = WebSocketPool(logger=self.logger)
        self.default_cookies = cookies or {}
        self.update_session_cookies(self.default_cookies)
        self._lock = asyncio.Lock()

        retry_times = self.settings.MAX_REQ_TIMES
        retry_delay = self.settings.DELAY_REQ_TIME
        self.retryer = AsyncRetrying(
            stop=stop_after_attempt(retry_times),
            wait=wait_fixed(retry_delay),
            retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
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
            "impersonate": request.impersonate,
            "ja3": request.ja3,
            "akamai": request.akamai,
        }
        if request.data:
            args["data"] = request.data
        args.update({k: v for k, v in request.kwargs.items() if k != "json"})
        return args
    
    async def do_request(self, session: requests.AsyncSession, request: Union["HttpRequest", "WebSocketRequest"], is_ws=False):
        async for attempt in self.retryer:
            with attempt:
                if is_ws:
                    return await self.ws_connect_once(session, request)
                else:
                    return await self.do_request_once(session, request)
                
    async def media_req(self, session: requests.AsyncSession, request: MediaRequest):
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
            single_part_response: "Response" = await session.request(
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
    
    async def do_request_once(self, session: requests.AsyncSession, request: "HttpRequest"):
        if isinstance(request, MediaRequest):
            return await self.media_req(session=session, request=request)
        
        method: Literal["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH"] = request.method
        raw_response = await session.request(
            method=method,
            **self._build_request_args(request)
        )
        return raw_response
    
    async def ws_connect_once(self, session: requests.AsyncSession, request: "WebSocketRequest"):
        websocket: "requests.websockets.WebSocket" = await session.ws_connect(url=request.url, 
            headers=request.headers, 
            cookies=request.cookies if request.cookies else session.cookies.get_dict(), 
            proxies=request.proxies, 
            timeout=request.timeout,
            allow_redirects=request.allow_redirects,
            max_redirects=request.max_redirects,
            verify=request.verify,
            impersonate=request.impersonate,
            ja3=request.ja3,
            akamai=request.akamai,
            **request.kwargs
        )
        # Automatic pinging is built-in, but curl_cffi lacks `ping_data` config,
        # so manual protocol-level ping frames cannot be sent.
        return websocket
    
    def get_websocket(self, url: str) -> WebSocketEntry:
        return self.websocket_pool.get_from_url(url)
    
    def init_websocket(self, url: str, task: asyncio.Task, queue: asyncio.Queue) -> str: # return websocket_id
        return self.websocket_pool.init_websocket(end_tag=self.settings.WS_END_TAG, url=url, task=task, queue=queue)

    def set_websocket(self, url: str, websocket: requests.websockets.WebSocket) -> str: # return websocket_id
        return self.websocket_pool.set_websocket(url=url, websocket=websocket)

    def update_session_cookies(self, cookies_dict: Dict):
        for ck, val in cookies_dict.items():
            self.session.cookies.set(ck, val)

    async def session_close(self):
        await self.session.close()

    async def close_websocket(self, key: str):
        entry = self.websocket_pool.get_from_key(key)
        if entry:
            await entry.close()
            self.websocket_pool.remove(key)

class SessionManager:
    """
    The central manager for all sessions running within a single-threaded asyncio event loop.
    Maintains a mapping from session IDs to SessionWrapper instances and groups of session IDs.
    Tracks reference counts for each session to manage usage, marks sessions as ended when tasks complete, and queues sessions for safe asynchronous cleanup via a background reaper loop.
    Provides methods to get/create sessions, batch register sessions with cookies, acquire/release sessions references, mark sessions as ended, and close sessions/groups safely without concurrency issues.
    """
    def __init__(self, stop_event=None, settings=None):
        self._default_session_id = create_uniqueId()
        self._sessions: Dict[str, SessionWrapper] = {self._default_session_id: None}
        self._group_sessions: Dict[str, List[str]] = {}

        self.stop_event: asyncio.Event = stop_event
        self.settings: "SettingsInfo" = settings

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
        from ..utils import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event, 
            settings=crawler.settings,
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
            return wrapper

        wrapper = SessionWrapper(stop_event=self.stop_event, settings=self.settings, cookies=cookies)
        self._sessions[session_id] = wrapper
        return wrapper
    
    def register_sessions_batch(self, user_cookies: Dict[str, Dict], group_id: Optional[str] = None) -> str:
        if not user_cookies:
            return

        group_id = group_id or create_uniqueId()
        session_ids = []

        for session_id, cookies in user_cookies.items():
            if session_id not in self._sessions:
                wrapper = SessionWrapper(settings=self.settings, cookies=cookies)
                self._sessions[session_id] = wrapper
                session_ids.append(session_id)
            else:
                self.logger.info(f"[SessionManager] Session {session_id} already exists, skipped.")

        self._group_sessions[group_id] = session_ids
        self.logger.debug(f"[SessionManager] Registered group '{group_id}' with sessions: {session_ids}")
        return group_id
    
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
        if self.is_default_session(session_id) or (not session_id):
            return
        wrapper = self._sessions.pop(session_id, None)
        if wrapper:
            self.logger.debug(f"[SessionManager] Closing session: {session_id}")
            await wrapper.websocket_pool.close_all()
            await wrapper.session_close()

    async def session_end_cookies(self, session_id: str) -> Union[Dict, None]:
        wrapper = self._sessions.get(session_id)
        if wrapper:
            ret_cookies = {session_id: wrapper.session.cookies.get_dict()}
            return ret_cookies

    async def close_all(self) -> None:
        await asyncio.gather(*[self._safe_close(session_id) for session_id in list(self._sessions.keys())])
        self._sessions.clear()
        self._ref_counts.clear()
        self._end_flags.clear()
        self._pending_close_set.clear()
        while not self._close_queue.empty():
            self._close_queue.get_nowait()
            self._close_queue.task_done()