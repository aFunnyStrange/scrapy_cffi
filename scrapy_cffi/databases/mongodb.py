import asyncio
import inspect
from functools import wraps
from typing import Optional, TYPE_CHECKING, cast
try:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
    from pymongo.errors import AutoReconnect, ConnectionFailure, NetworkTimeout
except ImportError as e:
    raise ImportError(
        "Missing motor dependencies. "
        "Please install: pip install motor>=3.7.1"
    ) from e
if TYPE_CHECKING:
    from ..crawler import Crawler
    from ..models.databases import MongodbInfo

from ..utils.reconnect import AsyncReconnectController, reconnectable

RETRYABLE_EXCEPTIONS = (AutoReconnect, ConnectionFailure, NetworkTimeout)

class MongoCollectionWrapper:
    def __init__(self, collection: AsyncIOMotorCollection, manager: "MongoDBManager"):
        self._collection = collection
        self._manager = manager

    def __getattr__(self, name: str):
        attr = getattr(self._collection, name)

        if not callable(attr) or not inspect.iscoroutinefunction(attr):
            return attr

        @wraps(attr)
        async def wrapper(*args, **kwargs):
            async def operation():
                collection = self._manager.db.get_collection(self._collection.name)
                method = getattr(collection, name)
                return await method(*args, **kwargs)

            return await self._manager._reconnect_controller.run(operation)
        return wrapper

class MongoDBManager:
    def __init__(self, stop_event: asyncio.Event, mongo_uri: str, db_name: Optional[str] = None):
        if not db_name:
            raise ValueError("MongoDBManager requires a valid db_name.")
        self.stop_event = stop_event
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self._reconnect_controller = AsyncReconnectController(
            self.stop_event,
            self._reconnect,
            RETRYABLE_EXCEPTIONS,
            label="MongoDB",
        )

    @classmethod
    def from_mongodb_info(cls, stop_event: asyncio.Event, info: "MongodbInfo"):
        if not info.resolved_url:
            raise ValueError("MongoDBManager.from_mongodb_info requires MONBODB_INFO.resolved_url")
        if not info.DB:
            raise ValueError("MongoDBManager requires DB name on MongodbInfo")
        return cls(
            stop_event=stop_event,
            mongo_uri=info.resolved_url,
            db_name=str(info.DB),
        )

    @classmethod
    def from_crawler(cls, crawler: "Crawler") -> "MongoDBManager":
        return cls.from_mongodb_info(crawler.stop_event, crawler.settings.MONBODB_INFO)

    async def _reconnect(self):
        if self.client:
            self.client.close()
        self.client = AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client[self.db_name]

    async def init(self):
        await self._reconnect()

    async def close(self):
        if self.client:
            self.client.close()

    def collection(self, name: str) -> AsyncIOMotorCollection:
        # The proxy deliberately advertises Motor's collection type so user code
        # keeps the complete Motor API completion in IDEs.
        return cast(
            AsyncIOMotorCollection,
            MongoCollectionWrapper(self.db.get_collection(name), self),
        )

    @reconnectable
    async def list_collections(self):
        return await self.db.list_collection_names()
    
    @reconnectable
    async def drop_database(self, db_name: Optional[str] = None):
        await self.client.drop_database(db_name or self.db_name)
