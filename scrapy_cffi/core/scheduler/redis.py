import asyncio, time
from . import BaseScheduler
from ..downloader.internet import Request
from typing import TYPE_CHECKING, List
# from ...utils import run_with_timeout
from ...extensions import signals
from ...models.api import SingalInfo
from ..sessions import SessionManager
if TYPE_CHECKING:
    from ...crawler import Crawler
    from ...settings import SettingsInfo
    from ...spiders import Spider
    from ...databases import RedisManager
    from ...extensions import SignalManager

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
        if not self.settings.RABBITMQ_INFO.DONT_FILTER and not self.redisManager:
            raise ValueError("used RedisScheduler must config settings.REDIS_INFO")
        
        if self.settings.DUPEFILTER:
            from ...utils import load_object
            dupefilter_cls = load_object(path=self.settings.DUPEFILTER)
            self.dupefilter = dupefilter_cls(settings=self.settings, redisManager=self.redisManager, **kwargs)
        else:
            from ...dupefilter.redis import RedisDupeFilter
            self.dupefilter = RedisDupeFilter(settings=self.settings, redisManager=self.redisManager, **kwargs)

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
    
    async def put(self, request: "Request", spider: "Spider", **kwargs):
        is_seen = await self.dupefilter.request_seen(request=request, spider=spider)
        if is_seen:
            async with self.sessions_lock:
                self.sessions.release(session_id=request.session_id)
            self.signalManager.send(signal=signals.request_dropped, data=SingalInfo(signal_time=time.time(), request=request, reason=f"filter: {request.url}"))
            return False
        else:
            res = await self.redisManager.rpush(self.get_queue_key(spider=spider), request.to_bytes())
            if res:
                self.signalManager.send(signal=signals.request_scheduled, data=SingalInfo(signal_time=time.time(), request=request))
                return True
            else:
                async with self.sessions_lock:
                    self.sessions.release(session_id=request.session_id)
                self.signalManager.send(signal=signals.request_dropped, data=SingalInfo(signal_time=time.time(), request=request, reason=f"insert redis error: {request.url}"))
                return False

    async def put_is_req(self, request: "Request", spider: "Spider", **kwargs):
        return await self.dupefilter.mark_sent(request=request, spider=spider, **kwargs)

    async def get(self, spider: "Spider"=None, **kwargs):
        request_bytes = await self.redisManager.dequeue_request(queue_key=self.get_queue_key(spider=spider))
        if request_bytes is None:
            queue_size = await self.redisManager.llen(self.get_queue_key(spider=spider))
            return queue_size
        return Request.from_bytes(request_bytes)
    
    async def get_start_req(self, spider: "Spider", **kwargs):
        request_bytes = await self.redisManager.dequeue_request(queue_key=getattr(spider, "redis_key", self.settings.QUEUE_NAME))
        if request_bytes is None:
            return None
        return request_bytes