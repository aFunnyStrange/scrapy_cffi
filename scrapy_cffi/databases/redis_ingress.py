from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Union

from ..models.redis_stream import RedisIngressMode, RedisStreamConsumerInfo

if TYPE_CHECKING:
    from ..databases.redis import RedisManager, RedisStreamMessage
    from ..settings import SettingsInfo
    from ..spiders import Spider


@dataclass(frozen=True)
class RedisIngressConfig:
    stream_key: str
    mode: RedisIngressMode
    group_name: Optional[str] = None
    consumer_name: Optional[str] = None
    field: str = "data"
    count: int = 1
    block_ms: int = 2000
    group_start_id: str = "0"
    read_id: str = ">"
    mkstream: bool = True
    auto_ack: bool = True

    @property
    def is_stream(self) -> bool:
        return self.mode == RedisIngressMode.STREAM or bool(self.group_name)


def _pick_spider_value(spider: Any, *names: str):
    for name in names:
        value = getattr(spider, name, None)
        if value is not None:
            return value
    return None


def resolve_redis_ingress(spider: "Spider", settings: "SettingsInfo") -> RedisIngressConfig:
    """
    Merge spider-level attributes with optional settings.REDIS_STREAM_INFO defaults.
    Priority: spider attribute > settings.REDIS_STREAM_INFO > framework fallback.
    """
    stream_defaults: Optional[RedisStreamConsumerInfo] = getattr(settings, "REDIS_STREAM_INFO", None)

    stream_key = _pick_spider_value(spider, "redis_key")
    if not stream_key:
        if stream_defaults and stream_defaults.STREAM_KEY:
            stream_key = stream_defaults.STREAM_KEY
        elif settings.QUEUE_NAME:
            stream_key = f"{settings.QUEUE_NAME}:{spider.name}:start"
        else:
            stream_key = f"{spider.name}_redis_start"

    mode_raw = _pick_spider_value(spider, "redis_start_mode")
    if mode_raw is None and stream_defaults:
        mode_raw = stream_defaults.MODE
    if isinstance(mode_raw, RedisIngressMode):
        mode = mode_raw
    else:
        mode = RedisIngressMode(str(mode_raw or RedisIngressMode.LIST.value))

    group_name = _pick_spider_value(spider, "redis_group", "redis_xgroup")
    if group_name is None and stream_defaults:
        group_name = stream_defaults.GROUP_NAME

    consumer_name = _pick_spider_value(spider, "redis_consumer", "redis_xconsumer")
    if consumer_name is None:
        if stream_defaults and stream_defaults.CONSUMER_NAME:
            consumer_name = stream_defaults.CONSUMER_NAME
        else:
            consumer_name = spider.name

    field = _pick_spider_value(spider, "redis_stream_field")
    if field is None and stream_defaults:
        field = stream_defaults.FIELD
    field = field or "data"

    count = _pick_spider_value(spider, "redis_stream_count")
    if count is None and stream_defaults:
        count = stream_defaults.COUNT
    count = int(count or 1)

    block_ms = _pick_spider_value(spider, "redis_stream_block_ms")
    if block_ms is None and stream_defaults:
        block_ms = stream_defaults.BLOCK_MS
    block_ms = int(block_ms or 2000)

    group_start_id = _pick_spider_value(spider, "redis_stream_group_start_id")
    if group_start_id is None and stream_defaults:
        group_start_id = stream_defaults.GROUP_START_ID
    group_start_id = group_start_id or "0"

    read_id = _pick_spider_value(spider, "redis_stream_read_id")
    if read_id is None and stream_defaults:
        read_id = stream_defaults.READ_ID
    read_id = read_id or ">"

    mkstream = _pick_spider_value(spider, "redis_stream_mkstream")
    if mkstream is None and stream_defaults:
        mkstream = stream_defaults.MKSTREAM
    mkstream = True if mkstream is None else bool(mkstream)

    auto_ack = _pick_spider_value(spider, "redis_stream_ack")
    if auto_ack is None and stream_defaults:
        auto_ack = stream_defaults.AUTO_ACK
    auto_ack = True if auto_ack is None else bool(auto_ack)

    if mode == RedisIngressMode.STREAM and not group_name:
        raise ValueError(
            "Redis stream mode requires consumer group name. "
            "Set spider.redis_group or settings.REDIS_STREAM_INFO.GROUP_NAME."
        )

    return RedisIngressConfig(
        stream_key=stream_key,
        mode=mode,
        group_name=group_name,
        consumer_name=consumer_name,
        field=field,
        count=count,
        block_ms=block_ms,
        group_start_id=group_start_id,
        read_id=read_id,
        mkstream=mkstream,
        auto_ack=auto_ack,
    )


async def dequeue_start_request(
    redis_manager: "RedisManager",
    config: RedisIngressConfig,
) -> Optional[Union[bytes, "RedisStreamMessage"]]:
    if config.is_stream:
        if not config.group_name:
            raise ValueError("Redis stream ingress requires group_name")
        return await redis_manager.dequeue_stream_request(
            stream_key=config.stream_key,
            group_name=config.group_name,
            consumer_name=config.consumer_name,
            field=config.field,
            count=config.count,
            block=config.block_ms,
            group_start_id=config.group_start_id,
            read_id=config.read_id,
            mkstream=config.mkstream,
        )
    return await redis_manager.dequeue_request(queue_key=config.stream_key)


async def ack_start_request(
    redis_manager: "RedisManager",
    config: RedisIngressConfig,
    message: "RedisStreamMessage",
) -> Optional[int]:
    if config.is_stream and config.group_name:
        return await redis_manager.ack_stream_request(message=message, group_name=config.group_name)
    return None


__all__ = [
    "RedisIngressConfig",
    "resolve_redis_ingress",
    "dequeue_start_request",
    "ack_start_request",
]
