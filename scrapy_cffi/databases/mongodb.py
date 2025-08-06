from tenacity import retry, wait_fixed, retry_if_exception_type
import asyncio
from functools import wraps
try:
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo.errors import AutoReconnect, ConnectionFailure
except ImportError as e:
    raise ImportError(
        "Missing motor dependencies. "
        "Please install: pip install motor"
    ) from e
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..crawler import Crawler

def mongo_auto_retry(func):
    @wraps(func)
    @retry(
        wait=wait_fixed(1),
        retry=retry_if_exception_type((AutoReconnect, ConnectionFailure)),
        reraise=True
    )
    async def wrapper(self, *args, **kwargs):
        if self.stop_event.is_set():
            raise asyncio.CancelledError("Stop event set, abort MongoDB operation")
        try:
            return await func(self, *args, **kwargs)
        except (AutoReconnect, ConnectionFailure):
            await self._reconnect()
            return await func(self, *args, **kwargs)
    return wrapper

class MongoDBManager:
    def __init__(self, stop_event: asyncio.Event, mongo_uri: str, db_name: str):
        self.stop_event = stop_event
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.client = None
        self.db = None

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            mongo_uri=crawler.settings.MONBODB_INFO.resolved_url,
            db_name=crawler.settings.MONBODB_INFO.DB
        )

    async def _reconnect(self):
        if self.client:
            self.client.close()
        self.client = AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client[self.db_name]

    async def init(self):
        await self._reconnect()

    @mongo_auto_retry
    async def insert_one(self, collection: str, document: dict):
        return await self.db[collection].insert_one(document)

    @mongo_auto_retry
    async def find_one(self, collection: str, filter: dict):
        return await self.db[collection].find_one(filter)

    @mongo_auto_retry
    async def update_one(self, collection: str, filter: dict, update: dict, upsert=False):
        return await self.db[collection].update_one(filter, update, upsert=upsert)

    @mongo_auto_retry
    async def delete_one(self, collection: str, filter: dict):
        return await self.db[collection].delete_one(filter)

    async def close(self):
        if self.client:
            self.client.close()
