"""Own crawler infrastructure repositories and their shared lifecycle."""

import asyncio
from typing import TYPE_CHECKING, Dict, Optional

from .resilience import ResourceSlot

if TYPE_CHECKING:
    from logging import Logger
    from ..repo.queue import KafkaQueueRepository, RabbitMQQueueRepository
    from ..repo.mongodb import MongoRepository
    from ..repo.redis import RedisRepository
    from ..repo.sql import SQLRepository


class ResourceService:
    """Publish typed repositories while centrally owning client lifecycle."""

    def __init__(self, logger: Optional["Logger"] = None) -> None:
        """Initialize an empty resource registry for the composition root."""
        self._logger = logger
        self.redis: Optional["RedisRepository"] = None
        self.mysql: Optional["SQLRepository"] = None
        self.postgres: Optional["SQLRepository"] = None
        self.mongodb: Optional["MongoRepository"] = None
        self.rabbitmq: Optional["RabbitMQQueueRepository"] = None
        self.kafka: Optional["KafkaQueueRepository"] = None
        self._slots: Dict[str, ResourceSlot] = {}
        self._started = False

    def register(self, name: str, slot: ResourceSlot, repository: object) -> None:
        """Register one concrete resource assembled by the composition root."""
        if name not in {"redis", "mysql", "postgres", "mongodb", "rabbitmq", "kafka"}:
            raise ValueError("Unsupported resource name: %s" % name)
        if name in self._slots:
            raise ValueError("Resource %s is already registered" % name)
        self._slots[name] = slot
        setattr(self, name, repository)

    async def start(self) -> None:
        """Start all registered resources and roll back partial startup."""
        if self._started:
            return
        try:
            await asyncio.gather(*(slot.start() for slot in self._slots.values()))
        except BaseException:
            await self.close()
            raise
        self._started = True

    async def close(self) -> None:
        """Close every resource exactly once."""
        slots = list(self._slots.items())
        if slots:
            results = await asyncio.gather(
                *(slot.close() for _, slot in reversed(slots)),
                return_exceptions=True,
            )
            if self._logger is not None:
                for (name, _), result in zip(reversed(slots), results):
                    if isinstance(result, BaseException):
                        self._logger.error(
                            "Failed to close %s resource: %r",
                            name,
                            result,
                        )
        self._started = False


__all__ = ["ResourceService"]
