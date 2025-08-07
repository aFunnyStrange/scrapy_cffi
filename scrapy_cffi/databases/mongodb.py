import asyncio
import inspect
from functools import wraps
from typing import Optional, Any, Callable, Coroutine, TYPE_CHECKING
try:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
except ImportError as e:
    raise ImportError(
        "Missing motor dependencies. "
        "Please install: pip install motor>=3.7.1"
    ) from e
if TYPE_CHECKING:
    from ..crawler import Crawler

RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError)

def auto_retry(func: Callable[..., Coroutine[Any, Any, Any]]):
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        if self.stop_event.is_set():
            raise asyncio.CancelledError("Stop event set, abort MongoDB operation")
        try:
            return await func(self, *args, **kwargs)
        except RETRYABLE_EXCEPTIONS:
            if self.stop_event.is_set():
                raise asyncio.CancelledError("Stop event set during reconnect")
            await self._reconnect()
            return await func(self, *args, **kwargs)
    return wrapper

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
            if self._manager.stop_event.is_set():
                raise asyncio.CancelledError("Stop event set, abort MongoDB operation")
            try:
                return await attr(*args, **kwargs)
            except RETRYABLE_EXCEPTIONS:
                if self._manager.stop_event.is_set():
                    raise asyncio.CancelledError("Stop event set during reconnect")
                await self._manager._reconnect()
                new_attr = getattr(self._manager.db.get_collection(self._collection.name), name)
                return await new_attr(*args, **kwargs)
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

    @classmethod
    def from_crawler(cls, crawler: "Crawler") -> "MongoDBManager":
        return cls(
            stop_event=crawler.stop_event,
            mongo_uri=crawler.settings.MONBODB_INFO.resolved_url,
            db_name=crawler.settings.MONBODB_INFO.DB,
        )

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
        return MongoCollectionWrapper(self.db.get_collection(name), self)

    @auto_retry
    async def list_collections(self):
        return await self.db.list_collection_names()
    
    @auto_retry
    async def drop_database(self, db_name: Optional[str] = None):
        await self.client.drop_database(db_name or self.db_name)
