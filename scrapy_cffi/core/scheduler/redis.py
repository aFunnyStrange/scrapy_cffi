import asyncio, time
from . import BaseScheduler
from ..downloader.internet import Request, WebSocketRequest
from typing import TYPE_CHECKING, List
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

class RedisScheduler(BaseScheduler):
    def __init__(
        self, 
        dupefilter_cls,
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
            dupefilter_cls=dupefilter_cls,
            spiders_name=spiders_name, 
            stop_event=stop_event, 
            settings=settings, 
            sessions=sessions, 
            sessions_lock=sessions_lock, 
            signalManager=signalManager, 
            **kwargs
        )
        self.redisManager = redisManager
        if self.redisManager.redis_mode == "cluster":
            self.cluster_nodes = [f"{n['host']}:{n['port']}" for n in self.redisManager._redis_url]
        else:
            self.cluster_nodes = ["None"]

        self.new_seen = self.settings._NEW_SEEN
        self.sent_seen = self.settings._SENT_SEEN
        if not self.redisManager:
            raise ValueError("used RedisScheduler must config settings.REDIS_INFO")
        self.is_distributed = True

    @classmethod
    def from_crawler(cls, crawler: "Crawler", dupefilter_cls, spiders_name: List):
        return cls(
            dupefilter_cls=dupefilter_cls,
            spiders_name=spiders_name, 
            stop_event=crawler.stop_event,
            settings=crawler.settings,
            sessions=crawler.sessions,
            sessions_lock=crawler.sessions_lock,
            signalManager=crawler.signalManager,
            redisManager=crawler.redisManager
        )
    
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
            fingerprint = self.dupefilter.get_fingerprint(request=request)

            if self.redisManager.redis_mode == "cluster":
                # cluster
                from ...utils import get_node

                node = get_node(self.cluster_nodes, fingerprint)

                key_new_seen_node = f"{self.new_seen}:{node}"
                key_is_req_node = f"{self.sent_seen}:{node}"

                res = await self.redisManager.push_if_not_seen(
                    fp=fingerprint,
                    req_bytes=request.to_bytes(),
                    key_new_seen=key_new_seen_node,
                    key_is_req=key_is_req_node,
                    queue_key=self.get_queue_key(spider=spider)
                )
            else:
                # single / sentinel
                res = await self.redisManager.push_if_not_seen(
                    fp=fingerprint,
                    req_bytes=request.to_bytes(),
                    key_new_seen=self.new_seen,
                    key_is_req=self.sent_seen,
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
            await self.redisManager.sadd(self.sent_seen, self.dupefilter.get_fingerprint(request=request))

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