import asyncio, time
from . import BaseScheduler
from ..downloader.internet import Request
from typing import TYPE_CHECKING, List, Optional
# from ...utils import run_with_timeout
from ...extensions import signals, SignalInfo
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
    def from_crawler(cls, crawler: "Crawler", spiders_name: List, spider_classes: Optional[List[type]] = None):
        return cls(
            spiders_name=spiders_name,
            spider_classes=spider_classes,
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
            self.signalManager.send(signal=signals.request_dropped, data=SignalInfo(signal_time=time.time(), request=request, reason=f"filter: {request.url}"))
            return False
        else:
            res = await self.redisManager.rpush(self.get_queue_key(spider=spider), request.to_bytes())
            if res:
                self.signalManager.send(signal=signals.request_scheduled, data=SignalInfo(signal_time=time.time(), request=request))
                return True
            else:
                async with self.sessions_lock:
                    self.sessions.release(session_id=request.session_id)
                self.signalManager.send(signal=signals.request_dropped, data=SignalInfo(signal_time=time.time(), request=request, reason=f"insert redis error: {request.url}"))
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
        queue_key = getattr(spider, "redis_key", None)
        if not queue_key:
            if self.settings.QUEUE_NAME:
                queue_key = f"{self.settings.QUEUE_NAME}:{spider.name}:start"
            else:
                queue_key = f"{spider.name}_redis_start"
        start_mode = getattr(spider, "redis_start_mode", "list")
        group_name = getattr(spider, "redis_group", None) or getattr(spider, "redis_xgroup", None)
        if start_mode == "stream" or group_name:
            if not group_name:
                raise ValueError("Redis stream mode requires spider.redis_group or spider.redis_xgroup")
            request_bytes = await self.redisManager.dequeue_stream_request(
                stream_key=queue_key,
                group_name=group_name,
                consumer_name=getattr(spider, "redis_consumer", None) or getattr(spider, "redis_xconsumer", None) or spider.name,
                field=getattr(spider, "redis_stream_field", "data"),
                count=getattr(spider, "redis_stream_count", 1),
                block=getattr(spider, "redis_stream_block_ms", 2000),
                group_start_id=getattr(spider, "redis_stream_group_start_id", "0"),
                read_id=getattr(spider, "redis_stream_read_id", ">"),
                mkstream=getattr(spider, "redis_stream_mkstream", True),
            )
            return request_bytes

        request_bytes = await self.redisManager.dequeue_request(queue_key=queue_key)
        if request_bytes is None:
            return None
        return request_bytes

    async def ack_start_req(self, spider: "Spider", message, **kwargs):
        group_name = getattr(spider, "redis_group", None) or getattr(spider, "redis_xgroup", None)
        if group_name:
            return await self.redisManager.ack_stream_request(message=message, group_name=group_name)
