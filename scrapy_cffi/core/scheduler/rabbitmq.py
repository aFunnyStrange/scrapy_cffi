import asyncio, time
from .redis import RedisScheduler
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
        **kwargs
    ):
        super().__init__(
            spiders_name=spiders_name, 
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
    def from_crawler(cls, crawler: "Crawler", spiders_name: List):
        return cls(
            spiders_name=spiders_name, 
            stop_event=crawler.stop_event,
            settings=crawler.settings,
            sessions=crawler.sessions,
            sessions_lock=crawler.sessions_lock,
            signalManager=crawler.signalManager,
            redisManager=crawler.redisManager,
            rabbitmqManager=crawler.rabbitmqManager
        )
    
    async def put(self, request: "Request", spider: "Spider", **kwargs):
        is_seen = await self.dupefilter.request_seen(request=request, spider=spider)
        if is_seen:
            async with self.sessions_lock:
                self.sessions.release(session_id=request.session_id)
            self.signalManager.send(signal=signals.request_dropped, data=SingalInfo(signal_time=time.time(), request=request, reason=f"filter: {request.url}"))
            return False
        else:
            res = await self.rabbitmqManager.rpush(self.get_queue_key(spider=spider), request.to_bytes())
            if res:
                self.signalManager.send(signal=signals.request_scheduled, data=SingalInfo(signal_time=time.time(), request=request))
                return True
            else:
                async with self.sessions_lock:
                    self.sessions.release(session_id=request.session_id)
                self.signalManager.send(signal=signals.request_dropped, data=SingalInfo(signal_time=time.time(), request=request, reason=f"insert redis error: {request.url}"))
                return False

    async def get(self, spider: "Spider"=None, **kwargs):
        request_bytes = await self.rabbitmqManager.dequeue_request(queue_name=self.get_queue_key(spider=spider))
        if request_bytes is None:
            queue_size = await self.rabbitmqManager.llen(self.get_queue_key(spider=spider))
            return queue_size
        return Request.from_bytes(request_bytes)
    
    async def get_start_req(self, spider: "Spider", **kwargs):
        request_bytes = await self.rabbitmqManager.dequeue_request(queue_name=getattr(spider, "rabbitmq_queue", self.settings.QUEUE_NAME))
        if request_bytes is None:
            return None
        return request_bytes