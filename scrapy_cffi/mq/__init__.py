"""
Message queue adapters — usable standalone without the crawler framework.

Standalone:
    from scrapy_cffi.mq.rabbitmq import RabbitMQManager
    from scrapy_cffi.mq.kafka import KafkaManager
"""

from __future__ import annotations

import importlib
from typing import Any

_LAZY_EXPORTS = {
    "RabbitMQManager": (".rabbitmq", "RabbitMQManager"),
    "KafkaManager": (".kafka", "KafkaManager"),
    "KafkaMessage": (".kafka", "KafkaMessage"),
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_path, attr = _LAZY_EXPORTS[name]
        mod = importlib.import_module(module_path, __name__)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
