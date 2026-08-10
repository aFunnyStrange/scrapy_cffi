"""Expose concrete external-system adapters without retry policy."""

from importlib import import_module
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

if TYPE_CHECKING:
    from .kafka import KafkaClient, KafkaRecord
    from .mongodb import MongoClient
    from .rabbitmq import RabbitMQClient
    from .redis import RedisClient
    from .sqlalchemy import MySQLClient, PostgresClient, SqlAlchemyClient

_EXPORTS: Dict[str, Tuple[str, str]] = {
    "RedisClient": (".redis", "RedisClient"),
    "RabbitMQClient": (".rabbitmq", "RabbitMQClient"),
    "KafkaClient": (".kafka", "KafkaClient"),
    "KafkaRecord": (".kafka", "KafkaRecord"),
    "MongoClient": (".mongodb", "MongoClient"),
    "SqlAlchemyClient": (".sqlalchemy", "SqlAlchemyClient"),
    "MySQLClient": (".sqlalchemy", "MySQLClient"),
    "PostgresClient": (".sqlalchemy", "PostgresClient"),
}

__all__ = [
    "RedisClient",
    "RabbitMQClient",
    "KafkaClient",
    "KafkaRecord",
    "MongoClient",
    "SqlAlchemyClient",
    "MySQLClient",
    "PostgresClient",
]


def __getattr__(name: str) -> Any:
    """Load one optional infrastructure adapter on first access."""
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError("module %r has no attribute %r" % (__name__, name))
    module_name, attribute = target
    return getattr(import_module(module_name, __name__), attribute)


def __dir__() -> List[str]:
    """Return all typed infrastructure exports."""
    return list(__all__)
