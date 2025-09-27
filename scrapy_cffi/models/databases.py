from pydantic import model_validator, Field
from enum import Enum
from typing import Optional, Union, List
from .base import StrictValidatedModel

class BaseDBInfo(StrictValidatedModel):
    URL: Optional[str] = None
    HOST: Optional[str] = None
    PORT: Optional[Union[str, int]] = None
    USERNAME: Optional[str] = None
    PASSWORD: Optional[str] = None
    DB: Optional[Union[str, int]] = None

    @property
    def resolved_url(self) -> str:
        return self.URL if self.URL else None

class RedisInfo(BaseDBInfo):
    @model_validator(mode="after")
    def assemble_url(self) -> "RedisInfo":
        if not self.URL and self.HOST and self.PORT:
            auth_part = ""
            if self.USERNAME and self.PASSWORD:
                auth_part = f"{self.USERNAME}:{self.PASSWORD}@"
            elif self.PASSWORD:
                auth_part = f":{self.PASSWORD}@"
            db_part = f"/{self.DB}" if self.DB is not None else ""
            self.URL = f"redis://{auth_part}{self.HOST}:{self.PORT}{db_part}"
        return self

class RedisMode(str, Enum):
    SINGLE = "single"
    SENTINEL = "sentinel"
    CLUSTER = "cluster"
    
class RedisInfo(BaseDBInfo):
    MODE: RedisMode = RedisMode.SINGLE

    SENTINELS: Optional[List[tuple[str, int]]] = Field(default_factory=list)
    MASTER_NAME: Optional[str] = None  # sentinel 模式需要

    CLUSTER_NODES: Optional[List[dict]] = Field(default_factory=list)

    @model_validator(mode="after")
    def assemble_url(self) -> "RedisInfo":
        if self.MODE == RedisMode.SINGLE:
            if not self.URL and self.HOST and self.PORT:
                auth_part = ""
                if self.USERNAME and self.PASSWORD:
                    auth_part = f"{self.USERNAME}:{self.PASSWORD}@"
                elif self.PASSWORD:
                    auth_part = f":{self.PASSWORD}@"
                db_part = f"/{self.DB}" if self.DB is not None else ""
                self.URL = f"redis://{auth_part}{self.HOST}:{self.PORT}{db_part}"
        return self

    @property
    def resolved_url(self) -> Union[str, List[tuple[str, int]], List[dict], None]:
        if self.MODE == RedisMode.SINGLE:
            return self.URL
        elif self.MODE == RedisMode.SENTINEL:
            return self.SENTINELS
        elif self.MODE == RedisMode.CLUSTER:
            return self.CLUSTER_NODES
        return None

class MysqlInfo(BaseDBInfo):
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
    "RedisInfo",
    "MysqlInfo",
    "MongodbInfo",
]