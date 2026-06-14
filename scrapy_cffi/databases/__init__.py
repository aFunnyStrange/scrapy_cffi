"""
Database adapters — usable standalone without the crawler framework.

Standalone:
    from scrapy_cffi.databases.redis import RedisManager
    from scrapy_cffi.models import RedisInfo

Framework:
    manager = RedisManager.from_crawler(crawler)
"""

from .redis import RedisManager
from .mysql import SQLAlchemyMySQLManager
from .postgres import SQLAlchemyPostgresManager
from .mongodb import MongoDBManager
from .sqlalchemy_base import BaseSQLAlchemyManager, build_engine_kwargs
from . import redis_ingress

__all__ = [
    "RedisManager",
    "SQLAlchemyMySQLManager",
    "SQLAlchemyPostgresManager",
    "MongoDBManager",
    "BaseSQLAlchemyManager",
    "build_engine_kwargs",
    "redis_ingress",
]
