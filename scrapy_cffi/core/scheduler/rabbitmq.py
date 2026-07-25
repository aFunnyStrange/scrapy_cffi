import asyncio
from .redis import RedisScheduler
from ..downloader.internet import Request
from typing import TYPE_CHECKING, List, Optional
from ._signals import emit_request_dropped, emit_request_scheduled
from ..sessions import SessionManager
if TYPE_CHECKING:
    from ...crawler import Crawler
    from ...settings import SettingsInfo
    from ...spiders import Spider
    from ...databases import RedisManager
    from ...extensions import SignalManager
    from ...mq.rabbitmq import RabbitMQManager

class RabbitMqScheduler(RedisScheduler):
    def __init__(
        self, 
        spiders_name: List=None,
        stop_event: asyncio.Event=None, 
        settings: "SettingsInfo"=None, 
        sessions: "SessionManager"=None, 
        sessions_lock: asyncio.Lock=None, 
        signalManager: "SignalManager"=None, 
        redisManager: "RedisManager"=None, 
        rabbitmqManager: "RabbitMQManager"=None,
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
            redisManager=redisManager, 
            **kwargs
        )
        self.rabbitmqManager = rabbitmqManager

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
            rabbitmqManager=crawler.rabbitmqManager,
        )
    
    async def put(self, request: "Request", spider: "Spider", **kwargs):
        if request.dont_filter or request.meta.get("is_start_url"):
            request_bytes = await self._request_to_bytes(request, spider)
            res = await self.rabbitmqManager.rpush(self.get_queue_key(spider=spider), request_bytes)
            if res:
                await self._complete_start_request(request, spider)
                emit_request_scheduled(self.signalManager, request)
                return True
            async with self.sessions_lock:
                self.sessions.release(session_id=request.session_id)
            emit_request_dropped(self.signalManager, request, f"insert rabbitmq error: {request.url}")
            return False

        is_seen = await self.dupefilter.request_seen(request=request, spider=spider)
        if is_seen:
            async with self.sessions_lock:
                self.sessions.release(session_id=request.session_id)
            emit_request_dropped(self.signalManager, request, f"filter: {request.url}")
            return False
        else:
            request_bytes = await self._request_to_bytes(request, spider)
            res = await self.rabbitmqManager.rpush(self.get_queue_key(spider=spider), request_bytes)
            if res:
                await self._complete_start_request(request, spider)
                emit_request_scheduled(self.signalManager, request)
                return True
            else:
                async with self.sessions_lock:
                    self.sessions.release(session_id=request.session_id)
                emit_request_dropped(self.signalManager, request, f"insert rabbitmq error: {request.url}")
                return False

    async def get(self, spider: "Spider"=None, **kwargs):
        request_bytes = await self.rabbitmqManager.dequeue_request(queue_name=self.get_queue_key(spider=spider))
        if request_bytes is None:
            queue_size = await self.rabbitmqManager.llen(self.get_queue_key(spider=spider))
            return queue_size
        request = Request.from_bytes(request_bytes)
        await self._restore_request_session(request, spider)
        return self._lease_request(request)

    async def requeue_inflight(self, spider: "Spider") -> int:
        requeued = 0
        queue_key = self.get_queue_key(spider)
        for request_id, request in list(self._inflight_requests.items()):
            request_bytes = await self._request_to_bytes(request, spider)
            if await self.rabbitmqManager.rpush(queue_key, request_bytes):
                self._inflight_requests.pop(request_id, None)
                requeued += 1
        queue_name = getattr(spider, "rabbitmq_queue", None)
        if not queue_name:
            queue_name = f"{self.settings.QUEUE_NAME}:{spider.name}:start" if self.settings.QUEUE_NAME else f"{spider.name}_rabbit_start"
        for request_id, message in list(self._start_requests.items()):
            if await self.rabbitmqManager.rpush(queue_name, message):
                self._start_requests.pop(request_id, None)
                requeued += 1
        return requeued
    
    async def get_start_req(self, spider: "Spider", **kwargs):
        queue_name = getattr(spider, "rabbitmq_queue", None)
        if not queue_name:
            if self.settings.QUEUE_NAME:
                queue_name = f"{self.settings.QUEUE_NAME}:{spider.name}:start"
            else:
                queue_name = f"{spider.name}_rabbit_start"
        request_bytes = await self.rabbitmqManager.dequeue_request(queue_name=queue_name)
        if request_bytes is None:
            return None
        return request_bytes

    async def cleanup(self, spider: "Spider") -> None:
        """Remove non-persistent RabbitMQ request state owned by this spider."""
        queue_name = getattr(spider, "rabbitmq_queue", None)
        if not queue_name:
            queue_name = (
                f"{self.settings.QUEUE_NAME}:{spider.name}:start"
                if self.settings.QUEUE_NAME
                else f"{spider.name}_rabbit_start"
            )
        for name in {self.get_queue_key(spider), queue_name}:
            await self.rabbitmqManager.delete_queue(name)
