import asyncio, hashlib, json, time
from ..downloader.internet import Request, HttpRequest, WebSocketRequest
from typing import TYPE_CHECKING, Set, List, Dict
# from ...utils import run_with_timeout
from ...extensions import signals
from ...models.api import SingalInfo
from ..sessions import SessionManager
if TYPE_CHECKING:
    from ...crawler import Crawler
    from ...models.api import SettingsInfo
    from ...spiders import Spider
    from ...databases import RedisManager
    from ...extensions import SignalManager

class BaseScheduler:
    def __init__(
        self, 
        spiders_name: List=None,
        stop_event: asyncio.Event=None, 
        settings: "SettingsInfo"=None, 
        sessions: "SessionManager"=None, 
        sessions_lock: asyncio.Lock=None, 
        signalManager: "SignalManager"=None, 
        **kwargs
    ):
        self.spiders_name = spiders_name
        self.stop_event = stop_event
        self.settings = settings
        self.sessions = sessions
        self.sessions_lock = sessions_lock
        self.signalManager = signalManager
        self.include_headers = self.settings.INCLUDE_HEADERS
        self.kwargs = kwargs
        self.is_distributed = False

    @classmethod
    def from_crawler(cls, crawler: "Crawler", spiders_name: List):
        return cls(
            spiders_name=spiders_name, 
            stop_event=crawler.stop_event,
            settings=crawler.settings,
            sessions=crawler.sessions,
            sessions_lock=crawler.sessions_lock,
            signalManager=crawler.signalManager
        )
    
    def get_queue_key(self, spider: "Spider") -> str:
        return None
    
    async def put(self, request: Request, spider: "Spider", **kwargs):
        raise NotImplementedError

    async def get(self, spider: "Spider"=None, **kwargs):
        raise NotImplementedError

    def get_fingerprint(self, request: "Request") -> str:
        fp = hashlib.sha1()
        if not isinstance(self.include_headers, list):
            raise ValueError("INCLUDE_HEADERS in settings is not list.")
        include_headers = {}
        for header_key in self.include_headers:
            has_header_key =  request.find_header_key(key=header_key)
            if has_header_key:
                include_headers[has_header_key.lower()] = request.headers[has_header_key]
        fp.update(f'{request.url}|{json.dumps(include_headers, separators=(",", ":"), sort_keys=True)}'.encode('latin-1'))
        if isinstance(request, HttpRequest):
            fp.update(f'{request.method}|'.encode('latin-1'))
            if isinstance(request.data, bytes):
                fp.update(request.data)
            elif isinstance(request.data, dict):
                fp.update(json.dumps(request.data, separators=(",", ":"), sort_keys=True).encode('latin-1'))
        elif isinstance(request, WebSocketRequest):
            fp.update(request.send_message)
        return fp.hexdigest()

class Scheduler(BaseScheduler):
    def __init__(
        self, 
        spiders_name: List=None,
        stop_event: asyncio.Event=None, 
        settings: "SettingsInfo"=None, 
        sessions: "SessionManager"=None, 
        sessions_lock: asyncio.Lock=None, 
        signalManager: "SignalManager"=None, 
        **kwargs
    ):
        super().__init__(
            spiders_name=spiders_name, 
            stop_event=stop_event, 
            settings=settings, 
            sessions=sessions, 
            sessions_lock=sessions_lock, 
            signalManager=signalManager, 
            **kwargs
        )
        self._queue_map: Dict[str, asyncio.Queue] = {}
        if self.settings.PROJECT_NAME:
            self._queue_map[self.settings.PROJECT_NAME] = asyncio.Queue()
        else:
            for spider_name in self.spiders_name:
                self._queue_map[f"{spider_name}_req"] = asyncio.Queue()
        self.filter_lock = asyncio.Lock()
        self.filter_new_seen_req_set = set() # Requests marked as seen but not yet sent
        self.filter_is_req_set = set() # Requests that have been seen and already sent

    def get_queue_key(self, spider: "Spider") -> str:
        return self.settings.PROJECT_NAME if self.settings.PROJECT_NAME else f"{spider.name}_req"

    async def put(self, request: Request, spider: "Spider", **kwargs):
        # Requests with dont_filter=True or WebSocket requests signaling connection end should not be deduplicated
        if request.dont_filter or (isinstance(request, WebSocketRequest) and request.websocket_end):
            await self._queue_map[self.get_queue_key(spider=spider)].put(request)
            self.signalManager.send(signal=signals.request_scheduled, data=SingalInfo(signal_time=time.time(), request=request))
            return True
        else:
            async with self.filter_lock:
                is_seen = self.request_seen(filter_set=self.filter_new_seen_req_set, request=request)
                if not is_seen:
                    await self._queue_map[self.get_queue_key(spider=spider)].put(request)
                    self.signalManager.send(signal=signals.request_scheduled, data=SingalInfo(signal_time=time.time(), request=request))
                    return True
                else:
                    async with self.sessions_lock:
                        self.sessions.release(session_id=request.session_id)
                    self.signalManager.send(signal=signals.request_dropped, data=SingalInfo(signal_time=time.time(), request=request, reason=f"filter: {request.url}"))
                    return False

    async def put_is_req(self, request: "Request", spider: "Spider", **kwargs):
        if not request.dont_filter:
            async with self.filter_lock:
                self.filter_is_req_set.add(self.get_fingerprint(request=request))

    async def get(self, spider: "Spider"=None, **kwargs):
        return await self._queue_map[self.get_queue_key(spider=spider)].get()

    def empty(self, spider: "Spider", **kwargs) -> bool:
        return self._queue_map[self.get_queue_key(spider=spider)].empty()
    
    def request_seen(self, filter_set: Set, request: "Request", **kwargs):
        fingerprint = self.get_fingerprint(request=request)
        is_seen = fingerprint in filter_set
        # If the request fingerprint is already in filter_set (i.e., seen before), return True.
        # Otherwise, add the fingerprint to filter_set and check if it is present in filter_is_req_set,
        # which indicates the request has already been dispatched.
        if is_seen:
            return is_seen
        filter_set.add(fingerprint)
        return fingerprint in self.filter_is_req_set

class RedisScheduler(BaseScheduler):
    def __init__(
        self, 
        spiders_name: List=None,
        stop_event: asyncio.Event=None, 
        settings: "SettingsInfo"=None, 
        sessions: "SessionManager"=None, 
        sessions_lock: asyncio.Lock=None, 
        signalManager: "SignalManager"=None, 
        redisManager: "RedisManager"=None, 
        **kwargs
    ):
        super().__init__(
            spiders_name=spiders_name, 
            stop_event=stop_event, 
            settings=settings, 
            sessions=sessions, 
            sessions_lock=sessions_lock, 
            signalManager=signalManager, 
            **kwargs
        )
        self.redisManager = redisManager
        self.filter_new_seen_req_key = self.settings._FILTER_NEW_SEEN_REQ_KEY
        self.filter_is_req_key = self.settings._FILTER_IS_REQ_KEY
        if not self.redisManager:
            raise ValueError("used RedisScheduler must config settings.REDIS_INFO")
        self.is_distributed = True

    @classmethod
    def from_crawler(cls, crawler: "Crawler", spiders_name: List):
        return cls(
            spiders_name=spiders_name, 
            stop_event=crawler.stop_event,
            settings=crawler.settings,
            sessions=crawler.sessions,
            sessions_lock=crawler.sessions_lock,
            signalManager=crawler.signalManager,
            redisManager=crawler.redisManager
        )
    
    def get_queue_key(self, spider: "Spider") -> str:
        return self.settings.PROJECT_NAME if self.settings.PROJECT_NAME else f"{spider.name}_req"

    async def put(self, request: "Request", spider: "Spider", **kwargs):
        # Requests with dont_filter=True or WebSocket requests signaling connection end should not be deduplicated
        if request.dont_filter or (isinstance(request, WebSocketRequest) and request.websocket_end):
            res = await self.redisManager.rpush(self.get_queue_key(spider=spider), request.to_bytes())
            if res:
                self.signalManager.send(signal=signals.request_scheduled, data=SingalInfo(signal_time=time.time(), request=request))
                return True
            else:
                async with self.sessions_lock:
                    self.sessions.release(session_id=request.session_id)
                self.signalManager.send(signal=signals.request_dropped, data=SingalInfo(signal_time=time.time(), request=request, reason=f"insert redis error: {request.url}"))
                return False
        else:
            fingerprint = self.get_fingerprint(request=request)
            res = await self.redisManager.push_if_not_seen(
                fp=fingerprint,
                req_bytes=request.to_bytes(),
                key_new_seen=self.filter_new_seen_req_key,
                key_is_req=self.filter_is_req_key,
                queue_key=self.get_queue_key(spider=spider)
            )
            if res:
                self.signalManager.send(signal=signals.request_scheduled, data=SingalInfo(signal_time=time.time(), request=request))
                return True
            else:
                async with self.sessions_lock:
                    self.sessions.release(session_id=request.session_id)
                self.signalManager.send(signal=signals.request_dropped, data=SingalInfo(signal_time=time.time(), request=request, reason=f"filter: {request.url}"))
                return False

    async def put_is_req(self, request: "Request", spider: "Spider", **kwargs):
        if not request.dont_filter:
            await self.redisManager.sadd(self.filter_is_req_key, self.get_fingerprint(request=request))

    async def get(self, spider: "Spider"=None, **kwargs):
        request_bytes = await self.redisManager.dequeue_request(queue_key=self.get_queue_key(spider=spider))
        if request_bytes is None:
            queue_size = await self.redisManager.llen(self.get_queue_key(spider=spider))
            return queue_size
        return Request.from_bytes(request_bytes)
    
    async def get_start_req(self, spider: "Spider", **kwargs):
        request_bytes = await self.redisManager.dequeue_request(queue_key=getattr(spider, "redis_key", self.settings.PROJECT_NAME))
        if request_bytes is None:
            return None
        return request_bytes