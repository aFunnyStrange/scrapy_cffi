import asyncio
import re
from typing import TYPE_CHECKING, List, Optional

from .redis import RedisScheduler
from ._signals import emit_request_dropped, emit_request_scheduled
from ..downloader.internet import Request

if TYPE_CHECKING:
    from ...crawler import Crawler
    from ...mq.kafka import KafkaManager, KafkaMessage
    from ...settings import SettingsInfo
    from ...spiders import Spider


def _kafka_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", value)


class KafkaScheduler(RedisScheduler):
    """Redis-backed dedup/session state with Kafka request transport."""

    def __init__(
        self,
        spiders_name: List = None,
        kafkaManager: "KafkaManager" = None,
        spider_classes: Optional[List[type]] = None,
        **kwargs,
    ):
        super().__init__(
            spiders_name=spiders_name,
            spider_classes=spider_classes,
            **kwargs,
        )
        if not kafkaManager:
            raise ValueError("KafkaScheduler requires settings.KAFKA_INFO to be configured")
        self.kafkaManager = kafkaManager
        self._inflight_messages = {}
        self._start_messages = {}

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
            kafkaManager=crawler.kafkaManager,
        )

    def get_queue_key(self, spider: "Spider") -> str:
        explicit = getattr(spider, "kafka_topic", None)
        return _kafka_name(explicit or super().get_queue_key(spider))

    def get_start_topic(self, spider: "Spider") -> str:
        explicit = getattr(spider, "kafka_start_topic", None)
        return _kafka_name(explicit or f"{self.get_queue_key(spider)}_start")

    def get_consumer_group(self, spider: "Spider", *, start: bool = False) -> str:
        attr = "kafka_start_group" if start else "kafka_group"
        explicit = getattr(spider, attr, None)
        suffix = "start" if start else "work"
        base = self.settings.KAFKA_INFO.CONSUMER_GROUP
        return explicit or f"{base}.{spider.name}.{suffix}"

    async def put(self, request: Request, spider: "Spider", **kwargs):
        if not (request.dont_filter or request.meta.get("is_start_url")):
            if await self.dupefilter.request_seen(request=request, spider=spider):
                async with self.sessions_lock:
                    self.sessions.release(session_id=request.session_id)
                emit_request_dropped(self.signalManager, request, f"filter: {request.url}")
                return False

        request_bytes = await self._request_to_bytes(request, spider)
        key = request.session_id.encode("utf-8") if request.session_id else None
        result = await self.kafkaManager.produce(
            self.get_queue_key(spider),
            request_bytes,
            key=key,
        )
        if result is not None:
            start_message = self._start_messages.pop(id(request), None)
            if start_message is not None:
                await self.kafkaManager.ack_request(start_message)
            emit_request_scheduled(self.signalManager, request)
            return True
        async with self.sessions_lock:
            self.sessions.release(session_id=request.session_id)
        emit_request_dropped(self.signalManager, request, f"insert kafka error: {request.url}")
        return False

    async def get(self, spider: "Spider" = None, **kwargs):
        message = await self.kafkaManager.dequeue_request(
            topic=self.get_queue_key(spider),
            consumer_group=self.get_consumer_group(spider),
        )
        if message is None:
            return 0
        request = Request.from_bytes(message.value)
        await self._restore_request_session(request, spider)
        self._inflight_messages[id(request)] = message
        return request

    async def complete_request(self, request: Request, spider: "Spider" = None) -> None:
        message = self._inflight_messages.pop(id(request), None)
        if message is not None:
            await self.kafkaManager.ack_request(message)

    async def requeue_inflight(self, spider: "Spider") -> int:
        # Manual Kafka offsets remain uncommitted and are replayed after the
        # consumer closes; producing duplicates here would be incorrect.
        return 0

    async def get_start_req(self, spider: "Spider", **kwargs):
        return await self.kafkaManager.dequeue_request(
            topic=self.get_start_topic(spider),
            consumer_group=self.get_consumer_group(spider, start=True),
        )

    def attach_start_req(self, request: Request, message: "KafkaMessage") -> None:
        self._start_messages[id(request)] = message

    async def ack_start_req(self, spider: "Spider", message: "KafkaMessage", **kwargs):
        return await self.kafkaManager.ack_request(message)

    async def cleanup(self, spider: "Spider") -> None:
        """Remove non-persistent Kafka request state owned by this spider."""
        await self.kafkaManager.delete_topics(
            [self.get_queue_key(spider), self.get_start_topic(spider)]
        )


__all__ = ["KafkaScheduler"]
