"""Define validated RabbitMQ and Kafka connection settings."""

from pydantic import Field, model_validator
from enum import Enum
from typing import Any, Optional, Union, List
from ..models.base import StrictValidatedModel

class QueueTopology(str, Enum):
    """List supported multi-endpoint queue deployment modes."""
    SINGLE = "single"
    CLUSTER = "cluster"

class QueueConnectionInfo(StrictValidatedModel):
    """Store shared endpoint fields for message-oriented systems."""
    DRIVER: Optional[str] = "amqp"
    URL: Optional[str] = None
    HOST: Optional[str] = None
    PORT: Optional[Union[str, int]] = None
    USERNAME: Optional[str] = None
    PASSWORD: Optional[str] = None
    MODE: Union[QueueTopology, str] = QueueTopology.SINGLE
    CLUSTER_NODES: Optional[List[str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def assemble_url(self) -> "QueueConnectionInfo":
        """Assemble a URL and infer cluster mode from configured nodes."""
        if not self.URL and self.HOST and self.PORT:
            auth_part = ""
            if self.USERNAME and self.PASSWORD:
                auth_part = f"{self.USERNAME}:{self.PASSWORD}@"
            elif self.PASSWORD:
                auth_part = f":{self.PASSWORD}@"
            self.URL = f"{self.DRIVER}://{auth_part}{self.HOST}:{self.PORT}"
        if self.CLUSTER_NODES:
            object.__setattr__(self, "MODE", QueueTopology.CLUSTER)
        return self

    @property
    def resolved_url(self) -> Union[str, List[str], None]:
        """Return one URL or the configured cluster endpoints."""
        if self.MODE == QueueTopology.SINGLE:
            return self.URL
        elif self.MODE == QueueTopology.CLUSTER:
            return self.CLUSTER_NODES
        return None

class RabbitMQInfo(QueueConnectionInfo):
    """Configure RabbitMQ connections, exchanges, and delivery behavior."""
    VHOST: str = "/"
    EXCHANGE_NAME: str = "scrapy_cffi"
    EXCHANGE_TYPE: str = "direct"
    PREFETCH_COUNT: int = 10
    DONT_FILTER: bool = False
    CONNECTION_TIMEOUT: float = 10.0
    HEARTBEAT: int = 60

    @model_validator(mode="after")
    def assemble_url(self) -> "RabbitMQInfo":
        """Assemble the RabbitMQ URL and append its virtual host."""
        super().assemble_url()
        if self.URL and self.VHOST:
            vhost_part = f"/{self.VHOST.strip('/')}"
            if not self.URL.endswith(vhost_part):
                self.URL = f"{self.URL}{vhost_part}"
        return self

class KafkaInfo(QueueConnectionInfo):
    """Configure Kafka clients, security, topics, and consumer defaults."""
    DRIVER: Optional[str] = None
    CONSUMER_GROUP: str = "scrapy_cffi"
    PERSISTENT_TIME: int = 7*24*60*60*1000
    NUM_PARTITIONS: int = 3
    REPLICATION_FACTOR: Optional[int] = None
    AUTO_OFFSET_RESET: str = "earliest"
    CLIENT_ID: str = "scrapy_cffi"
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
        """Assemble a Kafka bootstrap server without an AMQP-style scheme."""
        if isinstance(data, dict) and not data.get("URL") and data.get("HOST") and data.get("PORT"):
            data = dict(data)
            data["URL"] = f"{data['HOST']}:{data['PORT']}"
        return data

    @model_validator(mode="after")
    def normalize_cluster(self) -> "KafkaInfo":
        """Infer and validate the Kafka replication factor."""
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
    "QueueConnectionInfo",
    "QueueTopology",
    "RabbitMQInfo",
    "KafkaInfo",
]
