from pydantic import Field, model_validator
from enum import Enum
from typing import Any, Optional, Union, List
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
    MODE: Union[MQMode, str] = MQMode.SINGLE
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
        if self.CLUSTER_NODES:
            object.__setattr__(self, "MODE", MQMode.CLUSTER)
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
    EXCHANGE_NAME: Optional[str] = "scrapy_cffi"
    EXCHANGE_TYPE: Optional[str] = "direct"
    PREFETCH_COUNT: Optional[int] = 10
    DONT_FILTER: Optional[bool] = False
    CONNECTION_TIMEOUT: float = 10.0
    HEARTBEAT: int = 60

    @model_validator(mode="after")
    def assemble_url(self) -> "RabbitMQInfo":
        super().assemble_url()
        if self.URL and self.VHOST:
            vhost_part = f"/{self.VHOST.strip('/')}"
            if not self.URL.endswith(vhost_part):
                self.URL = f"{self.URL}{vhost_part}"
        return self

class KafkaInfo(BaseMQInfo):
    DRIVER: Optional[str] = None
    CONSUMER_GROUP: Optional[str] = "scrapy_cffi"
    PERSISTENT_TIME: Optional[int] = 7*24*60*60*1000
    NUM_PARTITIONS: Optional[int] = 3
    REPLICATION_FACTOR: Optional[int] = None
    AUTO_OFFSET_RESET: Optional[str] = "earliest"
    CLIENT_ID: Optional[str] = "scrapy_cffi"
    REQUEST_TIMEOUT_MS: int = 40000
    SECURITY_PROTOCOL: str = "PLAINTEXT"
    SASL_MECHANISM: Optional[str] = None
    SASL_USERNAME: Optional[str] = None
    SASL_PASSWORD: Optional[str] = None
    SSL_CAFILE: Optional[str] = None
    SSL_CERTFILE: Optional[str] = None
    SSL_KEYFILE: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def assemble_bootstrap_server(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("URL") and data.get("HOST") and data.get("PORT"):
            data = dict(data)
            data["URL"] = f"{data['HOST']}:{data['PORT']}"
        return data

    @model_validator(mode="after")
    def normalize_cluster(self) -> "KafkaInfo":
        super().assemble_url()
        if self.REPLICATION_FACTOR is None:
            object.__setattr__(
                self,
                "REPLICATION_FACTOR",
                len(self.CLUSTER_NODES) if self.CLUSTER_NODES else 1,
            )
        if self.REPLICATION_FACTOR < 1:
            raise ValueError("Kafka REPLICATION_FACTOR must be at least 1")
        if self.CLUSTER_NODES and self.REPLICATION_FACTOR > len(self.CLUSTER_NODES):
            raise ValueError("Kafka REPLICATION_FACTOR cannot exceed configured CLUSTER_NODES")
        return self

__all__ = [
    "RabbitMQInfo",
    "KafkaInfo",
]
