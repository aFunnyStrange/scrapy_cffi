import asyncio, time
from ..downloader.internet import Request
from typing import TYPE_CHECKING, List, Dict
# from ...utils import run_with_timeout
from ...extensions import signals
from ...models.api import SingalInfo
from ..sessions import SessionManager
if TYPE_CHECKING:
    from ...crawler import Crawler
    from ...settings import SettingsInfo
    from ...spiders import Spider
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
        return self.settings.QUEUE_NAME if self.settings.QUEUE_NAME else f"{spider.name}_req"
    
    async def put(self, request: Request, spider: "Spider", **kwargs):
        raise NotImplementedError

    async def get(self, spider: "Spider"=None, **kwargs):
        raise NotImplementedError

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
        if self.settings.DUPEFILTER:
            from ...utils import load_object
            dupefilter_cls = load_object(path=self.settings.DUPEFILTER)
            self.dupefilter = dupefilter_cls(settings=self.settings, **kwargs)
        else:
            from ...dupefilter.base import MemoryDupeFilter
            self.dupefilter = MemoryDupeFilter(settings=self.settings, **kwargs)
        self._queue_map: Dict[str, asyncio.Queue] = {}
        if self.settings.QUEUE_NAME:
            self._queue_map[self.settings.QUEUE_NAME] = asyncio.Queue()
        else:
            for spider_name in self.spiders_name:
                self._queue_map[f"{spider_name}_req"] = asyncio.Queue()

    async def put(self, request: Request, spider: "Spider", **kwargs):
        # Requests with dont_filter=True or WebSocket requests signaling connection end should not be deduplicated
        if request.dont_filter:
            await self._queue_map[self.get_queue_key(spider=spider)].put(request)
            self.signalManager.send(signal=signals.request_scheduled, data=SingalInfo(signal_time=time.time(), request=request))
            return True
        else:
            async with self.dupefilter.lock:
                is_seen = await self.dupefilter.request_seen(request=request)
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
        return await self.dupefilter.mark_sent(request=request, spider=spider, **kwargs)

    async def get(self, spider: "Spider"=None, **kwargs):
        return await self._queue_map[self.get_queue_key(spider=spider)].get()

    def empty(self, spider: "Spider", **kwargs) -> bool:
        return self._queue_map[self.get_queue_key(spider=spider)].empty()