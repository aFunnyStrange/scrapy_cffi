"""
Database adapters — usable standalone without the crawler framework.

Standalone:
    from scrapy_cffi.databases.redis import RedisManager
    from scrapy_cffi.models import RedisInfo

Framework:
    manager = RedisManager.from_crawler(crawler)

SQLAlchemy / Mongo managers are lazy-loaded so Redis-only crawlers do not
require optional database dependencies at import time.
"""

from __future__ import annotations

import importlib
from typing import Any

from .redis import RedisManager
from . import redis_ingress

_LAZY_EXPORTS = {
    "SQLAlchemyMySQLManager": (".mysql", "SQLAlchemyMySQLManager"),
    "SQLAlchemyPostgresManager": (".postgres", "SQLAlchemyPostgresManager"),
    "MongoDBManager": (".mongodb", "MongoDBManager"),
    "BaseSQLAlchemyManager": (".sqlalchemy_base", "BaseSQLAlchemyManager"),
    "build_engine_kwargs": (".sqlalchemy_base", "build_engine_kwargs"),
}

__all__ = [
    "RedisManager",
    "redis_ingress",
    *sorted(_LAZY_EXPORTS),
]


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_path, attr = _LAZY_EXPORTS[name]
        mod = importlib.import_module(module_path, __name__)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
