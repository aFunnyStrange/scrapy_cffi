"""
Standalone tool re-exports (no crawler / core engine).

Prefer explicit imports from ``scrapy_cffi.databases`` / ``scrapy_cffi.mq`` in libraries.
This namespace lazy-loads each symbol on first access.
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "RedisManager",
    "SQLAlchemyMySQLManager",
    "SQLAlchemyPostgresManager",
    "MongoDBManager",
    "BaseSQLAlchemyManager",
    "build_engine_kwargs",
    "redis_ingress",
    "RabbitMQManager",
    "KafkaManager",
    "canonical_request_url",
    "build_fingerprint_bytes",
    "fingerprint_sha1",
    "SettingsInfo",
    "merge_spider_settings",
]

_DATABASES = frozenset({
    "RedisManager",
    "SQLAlchemyMySQLManager",
    "SQLAlchemyPostgresManager",
    "MongoDBManager",
    "BaseSQLAlchemyManager",
    "build_engine_kwargs",
    "redis_ingress",
})

_MQ = frozenset({"RabbitMQManager", "KafkaManager"})

_FINGERPRINT = frozenset({
    "canonical_request_url",
    "build_fingerprint_bytes",
    "fingerprint_sha1",
})

_SETTINGS = frozenset({"SettingsInfo", "merge_spider_settings"})


def __getattr__(name: str):
    if name in _DATABASES:
        mod = import_module("scrapy_cffi.databases")
        return getattr(mod, name)
    if name in _MQ:
        mod = import_module("scrapy_cffi.mq")
        return getattr(mod, name)
    if name in _FINGERPRINT:
        mod = import_module("scrapy_cffi.dupefilter.fingerprint")
        return getattr(mod, name)
    if name in _SETTINGS:
        mod = import_module("scrapy_cffi.settings")
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return list(__all__)
