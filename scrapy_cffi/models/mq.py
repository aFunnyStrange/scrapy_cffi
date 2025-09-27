from pydantic import Field, model_validator
from enum import Enum
from typing import Optional, Union, List
from .base import StrictValidatedModel

class MQMode(str, Enum):
    SINGLE = "single"
    CLUSTER = "cluster"

class BaseMQInfo(StrictValidatedModel):
    DRIVER: Optional[str] = "amqp"
    URL: Optional[str] = None
    HOST: Optional[str] = None
    PORT: Optional[Union[str, int]] = None
    USERNAME: Optional[str] = None
    PASSWORD: Optional[str] = None
    MODE: MQMode = MQMode.SINGLE
    CLUSTER_NODES: Optional[List[str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def assemble_url(self) -> "BaseMQInfo":
        if not self.URL and self.HOST and self.PORT:
            auth_part = ""
            if self.USERNAME and self.PASSWORD:
                auth_part = f"{self.USERNAME}:{self.PASSWORD}@"
            elif self.PASSWORD:
                auth_part = f":{self.PASSWORD}@"
            self.URL = f"{self.DRIVER}://{auth_part}{self.HOST}:{self.PORT}"
        return self

    @property
    def resolved_url(self) -> Union[str, List[str], None]:
        if self.MODE == MQMode.SINGLE:
            return self.URL
        elif self.MODE == MQMode.CLUSTER:
            return self.CLUSTER_NODES
        return None

class RabbitMQInfo(BaseMQInfo):
    VHOST: Optional[str] = "/"
    EXCHANGE_NAME: str = "scrapy_cffi"
    EXCHANGE_TYPE: str = "direct"  # direct / fanout / topic / headers
    PREFETCH_COUNT: int = 10
    DONT_FILTER: bool = False

    @model_validator(mode="after")
    def assemble_url(self) -> "RabbitMQInfo":
        super().assemble_url()
        if self.URL and self.VHOST:
            vhost_part = f"/{self.VHOST.strip('/')}"
            if not self.URL.endswith(vhost_part):
                self.URL = f"{self.URL}{vhost_part}"
        return self

class KafkaInfo(BaseMQInfo):
    CONSUMER_GROUP: Optional[str] = "scrapy_cffi"
    PERSISTENT_TIME: Optional[int] = 24*60*60*7000

__all__ = [
    "RabbitMQInfo",
    "KafkaInfo",
]