"""Implement one-shot Motor client lifecycle without retry policy."""

from typing import Any, Optional

try:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
except ImportError as exc:
    raise ImportError("Missing Motor dependencies. Install motor>=3.7.1.") from exc

from ...config.database import MongodbInfo


class MongoClient:
    """Own one Motor client and selected database."""

    def __init__(self, mongo_uri: str, db_name: str) -> None:
        """Store MongoDB connection settings without connecting."""
        if not db_name:
            raise ValueError("MongoClient requires a valid db_name")
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Any = None

    @classmethod
    def from_info(cls, info: MongodbInfo) -> "MongoClient":
        """Create a client from validated MongoDB settings."""
        if not info.resolved_url or not info.DB:
            raise ValueError("MongoClient requires a URL and database name")
        return cls(info.resolved_url, str(info.DB))

    async def connect(self) -> None:
        """Create the reusable Motor client."""
        if self.client is not None:
            return
        self.client = AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client[self.db_name]

    async def close(self) -> None:
        """Close the Motor client."""
        client = self.client
        self.client = None
        self.db = None
        if client is not None:
            client.close()

    def collection(self, name: str) -> AsyncIOMotorCollection:
        """Return one native Motor collection."""
        if self.db is None:
            raise RuntimeError("MongoClient has not been started")
        return self.db.get_collection(name)

    async def drop_database(self, db_name: Optional[str] = None) -> None:
        """Drop one database through the active Motor client."""
        if self.client is None:
            raise RuntimeError("MongoClient has not been started")
        await self.client.drop_database(db_name or self.db_name)


__all__ = ["MongoClient"]
