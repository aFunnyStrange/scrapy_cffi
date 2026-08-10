"""Direct-debug MongoDB repository smoke flow."""

import asyncio

from scrapy_cffi import build_resource_service
from scrapy_cffi.config.database import MongodbInfo
from scrapy_cffi.settings import SettingsInfo


async def main() -> None:
    """Run one MongoDB collection flow."""
    settings = SettingsInfo(
        MONBODB_INFO=MongodbInfo(URL="mongodb://localhost:27017", DB="test_db")
    )
    resources = build_resource_service(settings, asyncio.Event())
    await resources.start()
    mongodb = resources.mongodb
    if mongodb is None:
        raise RuntimeError("MongoDB repository was not configured")
    try:
        collection = mongodb.collection("test_collection")
        await collection.create_index("name")
        await collection.insert_one({"name": "Alice", "age": 23})
        print(await collection.find_one({"name": "Alice"}))
        await mongodb.drop_database("test_db")
    finally:
        await resources.close()


if __name__ == "__main__":
    asyncio.run(main())
