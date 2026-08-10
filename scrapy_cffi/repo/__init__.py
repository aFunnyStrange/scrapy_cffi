"""Expose repositories lazily so optional drivers remain independent."""

from importlib import import_module
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

if TYPE_CHECKING:
    from .queue import KafkaQueueRepository, RabbitMQQueueRepository
    from .contracts import QueueMessage, RedisRepositoryProtocol, RequestQueueRepositoryProtocol
    from .mongodb import MongoRepository
    from .redis import RedisRepository, RedisStreamMessage
    from .sql import SQLRepository

_EXPORTS: Dict[str, Tuple[str, str]] = {
    "RedisRepositoryProtocol": (".contracts", "RedisRepositoryProtocol"),
    "RequestQueueRepositoryProtocol": (".contracts", "RequestQueueRepositoryProtocol"),
    "RedisRepository": (".redis", "RedisRepository"),
    "RedisStreamMessage": (".redis", "RedisStreamMessage"),
    "SQLRepository": (".sql", "SQLRepository"),
    "MongoRepository": (".mongodb", "MongoRepository"),
    "QueueMessage": (".contracts", "QueueMessage"),
    "KafkaQueueRepository": (".queue", "KafkaQueueRepository"),
    "RabbitMQQueueRepository": (".queue", "RabbitMQQueueRepository"),
}

__all__ = [
    "RedisRepositoryProtocol",
    "RequestQueueRepositoryProtocol",
    "RedisRepository",
    "RedisStreamMessage",
    "SQLRepository",
    "MongoRepository",
    "QueueMessage",
    "KafkaQueueRepository",
    "RabbitMQQueueRepository",
]


def __getattr__(name: str) -> Any:
    """Load one repository implementation on first access."""
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError("module %r has no attribute %r" % (__name__, name))
    module_name, attribute = target
    return getattr(import_module(module_name, __name__), attribute)


def __dir__() -> List[str]:
    """Return all typed repository exports."""
    return list(__all__)
