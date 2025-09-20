from .base import StrictValidatedModel
from pydantic import Field
from enum import Enum
from typing import Optional

class MQMode(str, Enum):
    SINGLE = "single"
    CLUSTER = "cluster"

class BaseMQInfo(StrictValidatedModel):
    URL: Optional[str] = None
    USERNAME: Optional[str] = None
    PASSWORD: Optional[str] = None
    VHOST: Optional[str] = "/"
    MODE: str = MQMode.SINGLE
    CLUSTER_NODES: Optional[list] = Field(default_factory=list)

class RabbitMQInfo(BaseMQInfo): pass

class KafkaInfo(BaseMQInfo): pass

__all__ = [
    "RabbitMQInfo",
    "KafkaInfo",
]