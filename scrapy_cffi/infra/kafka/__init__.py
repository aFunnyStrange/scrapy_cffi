"""Expose the optional Kafka infrastructure client."""

from .client import KafkaClient, KafkaRecord

__all__ = ["KafkaClient", "KafkaRecord"]
