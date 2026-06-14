import asyncio
from ..downloader.internet import Request
from typing import TYPE_CHECKING, List, Dict, Optional
from ._signals import emit_request_dropped, emit_request_scheduled
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
        spider_classes: Optional[List[type]] = None,
        **kwargs
    ):
        self.spiders_name = spiders_name or []
        self.stop_event = stop_event
        self.settings = settings
        self.sessions = sessions
        self.sessions_lock = sessions_lock
        self.signalManager = signalManager
        self.spider_classes_for_queues: List[type] = list(spider_classes) if spider_classes else []
        self.kwargs = kwargs
        self.is_distributed = False

    @classmethod
    def from_crawler(
        cls,
        crawler: "Crawler",
        spiders_name: List,
        spider_classes: Optional[List[type]] = None,
        settings: Optional["SettingsInfo"] = None,
    ):
        return cls(
            spiders_name=spiders_name,
            spider_classes=spider_classes,
            stop_event=crawler.stop_event,
            settings=settings or crawler.settings,
            sessions=crawler.sessions,
            sessions_lock=crawler.sessions_lock,
            signalManager=crawler.signalManager,
        )
    
    @staticmethod
    def queue_key_for_name(settings: "SettingsInfo", spider_name: str, spider_cls: type = None) -> str:
        """Stable queue/redis key for a spider name without an instance."""
        explicit = None
        if spider_cls is not None:
            explicit = getattr(spider_cls, "scheduler_queue_key", None) or getattr(spider_cls, "queue_name", None)
        if explicit:
            return explicit
        if settings.QUEUE_NAME:
            return f"{settings.QUEUE_NAME}:{spider_name}"
        return f"{spider_name}_req"

    def get_queue_key(self, spider: "Spider") -> str:
        explicit = getattr(spider, "scheduler_queue_key", None) or getattr(spider, "queue_name", None)
        if explicit:
            return explicit
        if self.settings.QUEUE_NAME:
            return f"{self.settings.QUEUE_NAME}:{spider.name}"
        return f"{spider.name}_req"
    
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
        spider_classes: Optional[List[type]] = None,
        **kwargs
    ):
        super().__init__(
            spiders_name=spiders_name,
            spider_classes=spider_classes,
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
        for i, spider_name in enumerate(self.spiders_name):
            spider_cls = self.spider_classes_for_queues[i] if i < len(self.spider_classes_for_queues) else None
            qk = BaseScheduler.queue_key_for_name(self.settings, spider_name, spider_cls)
            if qk not in self._queue_map:
                self._queue_map[qk] = asyncio.Queue()

    async def put(self, request: Request, spider: "Spider", **kwargs):
        # Requests with dont_filter=True or WebSocket requests signaling connection end should not be deduplicated
        if request.dont_filter:
            await self._queue_map[self.get_queue_key(spider=spider)].put(request)
            emit_request_scheduled(self.signalManager, request)
            return True
        else:
            async with self.dupefilter.lock:
                is_seen = await self.dupefilter.request_seen(request=request)
                if not is_seen:
                    await self._queue_map[self.get_queue_key(spider=spider)].put(request)
                    emit_request_scheduled(self.signalManager, request)
                    return True
                else:
                    async with self.sessions_lock:
                        self.sessions.release(session_id=request.session_id)
                    emit_request_dropped(self.signalManager, request, f"filter: {request.url}")
                    return False

    async def put_is_req(self, request: "Request", spider: "Spider", **kwargs):
        return await self.dupefilter.mark_sent(request=request, spider=spider, **kwargs)

    async def get(self, spider: "Spider"=None, **kwargs):
        return await self._queue_map[self.get_queue_key(spider=spider)].get()

    def empty(self, spider: "Spider", **kwargs) -> bool:
        return self._queue_map[self.get_queue_key(spider=spider)].empty()