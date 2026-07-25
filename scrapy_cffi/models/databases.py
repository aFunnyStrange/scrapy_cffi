from pydantic import model_validator, Field
from enum import Enum
from typing import Dict, Optional, Union, List, Tuple
from .base import StrictValidatedModel
from .redis_stream import RedisIngressMode, RedisStreamConsumerInfo


class BaseDBInfo(StrictValidatedModel):
    URL: Optional[str] = None
    HOST: Optional[str] = None
    PORT: Optional[Union[str, int]] = None
    USERNAME: Optional[str] = None
    PASSWORD: Optional[str] = None
    DB: Optional[Union[str, int]] = None

    @property
    def resolved_url(self) -> Optional[str]:
        return self.URL if self.URL else None


class SqlAlchemyEngineInfo(BaseDBInfo):
    ECHO: bool = False
    POOL_PRE_PING: bool = True
    POOL_SIZE: int = 5
    MAX_OVERFLOW: int = 10


class RedisMode(str, Enum):
    SINGLE = "single"
    SENTINEL = "sentinel"
    CLUSTER = "cluster"
    
class RedisInfo(BaseDBInfo):
    MODE: Union[RedisMode, str] = RedisMode.SINGLE

    SENTINELS: Optional[List[Tuple[str, int]]] = Field(default_factory=list)
    MASTER_NAME: Optional[str] = None  # sentinel mode
    SENTINEL_OVERRIDE_MASTER: Optional[Tuple[str, int]] = None # sentinel mode -> (master_host, master_port)

    CLUSTER_NODES: Optional[List[Union[dict, str]]] = Field(default_factory=list)
    CLUSTER_ADDRESS_REMAP: Dict[str, str] = Field(default_factory=dict)

    CONNECT_TIMEOUT: float = 5.0
    SOCKET_TIMEOUT: Optional[float] = None
    PROTOCOL: int = 2
    SSL: bool = False
    SSL_CERT_REQS: Optional[str] = None
    SENTINEL_USERNAME: Optional[str] = None
    SENTINEL_PASSWORD: Optional[str] = None

    @model_validator(mode="after")
    def assemble_url(self) -> "RedisInfo":
        has_sentinels = bool(self.SENTINELS)
        has_cluster_nodes = bool(self.CLUSTER_NODES)
        if has_sentinels and has_cluster_nodes:
            raise ValueError("Configure either SENTINELS or CLUSTER_NODES, not both")

        # Node lists are authoritative, so production configuration can switch
        # topology without repeating MODE in a separately managed secret file.
        if has_sentinels:
            object.__setattr__(self, "MODE", RedisMode.SENTINEL)
        elif has_cluster_nodes:
            object.__setattr__(self, "MODE", RedisMode.CLUSTER)

        mode = self.MODE.value if isinstance(self.MODE, RedisMode) else self.MODE
        if mode == RedisMode.SINGLE.value:
            if not self.URL and self.HOST and self.PORT:
                auth_part = ""
                if self.USERNAME and self.PASSWORD:
                    auth_part = f"{self.USERNAME}:{self.PASSWORD}@"
                elif self.PASSWORD:
                    auth_part = f":{self.PASSWORD}@"
                db_part = f"/{self.DB}" if self.DB is not None else ""
                scheme = "rediss" if self.SSL else "redis"
                self.URL = f"{scheme}://{auth_part}{self.HOST}:{self.PORT}{db_part}"
            elif self.URL and self.SSL and self.URL.startswith("redis://"):
                self.URL = f"rediss://{self.URL[len('redis://'):]}"
        return self

    @property
    def resolved_url(
        self,
    ) -> Optional[Union[str, List[Tuple[str, int]], List[Union[dict, str]]]]:
        if self.MODE == RedisMode.SINGLE:
            return self.URL
        elif self.MODE == RedisMode.SENTINEL:
            return self.SENTINELS
        elif self.MODE == RedisMode.CLUSTER:
            return self.CLUSTER_NODES
        return None

class MysqlInfo(SqlAlchemyEngineInfo):
    DRIVER: str = "mysql+asyncmy" # default driver

    @model_validator(mode="after")
    def assemble_url(self) -> "MysqlInfo":
        if not self.URL and self.HOST and self.PORT:
            auth_part = ""
            if self.USERNAME and self.PASSWORD:
                auth_part = f"{self.USERNAME}:{self.PASSWORD}@"
            elif self.PASSWORD:
                auth_part = f":{self.PASSWORD}@"
            db_part = f"/{self.DB}" if self.DB is not None else ""
            self.URL = f"{self.DRIVER}://{auth_part}{self.HOST}:{self.PORT}{db_part}"
        return self

class PostgresInfo(SqlAlchemyEngineInfo):
    DRIVER: str = "postgresql+asyncpg"

    @model_validator(mode="after")
    def assemble_url(self) -> "PostgresInfo":
        if not self.URL and self.HOST and self.PORT:
            auth_part = ""
            if self.USERNAME and self.PASSWORD:
                auth_part = f"{self.USERNAME}:{self.PASSWORD}@"
            elif self.PASSWORD:
                auth_part = f":{self.PASSWORD}@"
            db_part = f"/{self.DB}" if self.DB is not None else ""
            self.URL = f"{self.DRIVER}://{auth_part}{self.HOST}:{self.PORT}{db_part}"
        return self

class MongodbInfo(BaseDBInfo):
    @model_validator(mode="after")
    def assemble_url(self) -> "MongodbInfo":
        if not self.URL and self.HOST and self.PORT:
            auth_part = ""
            if self.USERNAME and self.PASSWORD:
                auth_part = f"{self.USERNAME}:{self.PASSWORD}@"
            elif self.PASSWORD:
                auth_part = f":{self.PASSWORD}@"
            db_part = f"/{self.DB}" if self.DB is not None else ""
            self.URL = f"mongodb://{auth_part}{self.HOST}:{self.PORT}{db_part}"
        return self

__all__ = [
    "BaseDBInfo",
    "SqlAlchemyEngineInfo",
    "RedisInfo",
    "RedisMode",
    "RedisIngressMode",
    "RedisStreamConsumerInfo",
    "MysqlInfo",
    "PostgresInfo",
    "MongodbInfo",
]
