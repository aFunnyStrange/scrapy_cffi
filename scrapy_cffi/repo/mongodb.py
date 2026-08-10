"""Implement MongoDB repository operations over a replaceable Motor client."""

from typing import Any, List, Optional

from ..infra.mongodb import MongoClient
from ..service.resilience import ResourceSlot, RetryPolicy


class MongoRepository:
    """Expose database-level MongoDB semantics with injected resilience."""

    def __init__(
        self,
        slot: ResourceSlot[MongoClient],
        retry_policy: RetryPolicy,
    ) -> None:
        """Bind MongoDB operations to one replaceable client slot."""
        self._slot = slot
        self._retry_policy = retry_policy

    @property
    def client(self) -> MongoClient:
        """Return the active MongoDB client adapter."""
        return self._slot.get()

    def collection(self, name: str) -> Any:
        """Return a native Motor collection for explicit advanced use."""
        return self.client.collection(name)

    async def _run(self, operation: Any) -> Any:
        """Execute one operation through the injected resilience service."""
        observed = {"generation": self._slot.generation}

        async def current_operation() -> Any:
            """Execute against and remember the active client generation."""
            observed["generation"] = self._slot.generation
            return await operation()

        return await self._retry_policy.run(
            current_operation,
            lambda: self._slot.replace(observed["generation"]),
        )

    async def list_collections(self) -> List[str]:
        """Return database collection names."""
        return list(await self._run(lambda: self.client.db.list_collection_names()))

    async def drop_database(self, db_name: Optional[str] = None) -> None:
        """Drop the selected database."""
        await self._run(lambda: self.client.drop_database(db_name))


__all__ = ["MongoRepository"]
