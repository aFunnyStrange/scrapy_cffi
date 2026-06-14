"""
Message queue adapters — usable standalone without the crawler framework.

Standalone:
    from scrapy_cffi.mq.rabbitmq import RabbitMQManager
    from scrapy_cffi.models import RabbitMQInfo

Framework:
    manager = RabbitMQManager.from_crawler(crawler)
"""

from .rabbitmq import RabbitMQManager
from .kafka import KafkaManager

__all__ = [
    "RabbitMQManager",
    "KafkaManager",
]
