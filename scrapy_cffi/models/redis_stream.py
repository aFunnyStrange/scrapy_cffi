from enum import Enum
from typing import Optional

from .base import StrictValidatedModel


class RedisIngressMode(str, Enum):
    LIST = "list"
    STREAM = "stream"


class RedisStreamConsumerInfo(StrictValidatedModel):
    """
    Optional defaults for RedisSpider ingress (list or stream consumer group).
    Spider class attributes still override these values when set.
    """

    MODE: RedisIngressMode = RedisIngressMode.LIST
    STREAM_KEY: Optional[str] = None
    GROUP_NAME: Optional[str] = None
    CONSUMER_NAME: Optional[str] = None
    FIELD: str = "data"
    COUNT: int = 1
    BLOCK_MS: int = 2000
    GROUP_START_ID: str = "0"
    READ_ID: str = ">"
    MKSTREAM: bool = True
    AUTO_ACK: bool = True


__all__ = [
    "RedisIngressMode",
    "RedisStreamConsumerInfo",
]
