import asyncio
from . import BaseScheduler
from ..downloader.internet import Request
from typing import TYPE_CHECKING, List, Optional
from ...databases.redis_ingress import (
    ack_start_request,
    dequeue_start_request,
    resolve_redis_ingress,
)
from ._signals import emit_request_dropped, emit_request_scheduled
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
        self.redisManager = redisManager
        if not self.redisManager:
            raise ValueError("RedisScheduler requires settings.REDIS_INFO to be configured")
        
        dedup_kw = {**kwargs}
        if self.spiders_name and len(self.spiders_name) == 1:
            dedup_kw.setdefault("redis_namespace", self.spiders_name[0])
        if self.settings.DUPEFILTER:
            from ...utils import load_object
            dupefilter_cls = load_object(path=self.settings.DUPEFILTER)
            self.dupefilter = dupefilter_cls(settings=self.settings, redisManager=self.redisManager, **dedup_kw)
        else:
            from ...dupefilter.redis import RedisDupeFilter
            self.dupefilter = RedisDupeFilter(settings=self.settings, redisManager=self.redisManager, **dedup_kw)

        self.is_distributed = True

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
            redisManager=crawler.redisManager,
        )
    
    async def put(self, request: "Request", spider: "Spider", **kwargs):
        # Ingress / start_urls: explicit tasks (redis RPUSH, spider.start), not link discoveries
        if request.dont_filter or request.meta.get("is_start_url"):
            res = await self.redisManager.rpush(self.get_queue_key(spider=spider), request.to_bytes())
            if res:
                emit_request_scheduled(self.signalManager, request)
                return True
            async with self.sessions_lock:
                self.sessions.release(session_id=request.session_id)
            emit_request_dropped(self.signalManager, request, f"insert redis error: {request.url}")
            return False

        is_seen = await self.dupefilter.request_seen(request=request, spider=spider)
        if is_seen:
            async with self.sessions_lock:
                self.sessions.release(session_id=request.session_id)
            emit_request_dropped(self.signalManager, request, f"filter: {request.url}")
            return False
        else:
            res = await self.redisManager.rpush(self.get_queue_key(spider=spider), request.to_bytes())
            if res:
                emit_request_scheduled(self.signalManager, request)
                return True
            else:
                async with self.sessions_lock:
                    self.sessions.release(session_id=request.session_id)
                emit_request_dropped(self.signalManager, request, f"insert redis error: {request.url}")
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
        ingress = resolve_redis_ingress(spider=spider, settings=self.settings)
        return await dequeue_start_request(self.redisManager, ingress)

    async def ack_start_req(self, spider: "Spider", message, **kwargs):
        ingress = resolve_redis_ingress(spider=spider, settings=self.settings)
        return await ack_start_request(self.redisManager, ingress, message)
