"""Define Redis list and Stream ingress settings."""

from enum import Enum
from typing import Optional

from ..models.base import StrictValidatedModel


class RedisIngressMode(str, Enum):
    """Select list polling or Redis Stream consumer-group ingress."""
    LIST = "list"
    STREAM = "stream"


class RedisStreamConsumerInfo(StrictValidatedModel):
    """Store optional RedisSpider ingress defaults overridden by spider fields."""

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
