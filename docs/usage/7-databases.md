# 1.Introduction
scrapy_cffi.databases provides adapter frameworks with automatic retry and reconnection utility classes for `Redis`, `MySQL`, and `MongoDB`. By default, `Redis` is included. For using the `MySQL` and `MongoDB` utility classes, you need to install the dependencies manually:
```bash
pip install sqlalchemy[asyncio] aiomysql
pip install motor>=3.7.1
```

# 2.Usage
`RedisManager` and `MongoDBManager` support seamless use of their native APIs. `SQLAlchemyMySQLManager` requires the use of the instance attributes `engine` and `session_factory`.

Specifically, once connected, `RedisManager` provides **full compatibility with the native `redis.asyncio` API**.

## 2.1 RedisManager
An async Redis client extending `redis.asyncio.Redis` with full API support.

**Features:**
- Automatically retries and reconnects on connection failures.
- Respects a global asyncio stop event to gracefully abort operations during shutdown.
- Only allows certain Redis commands (e.g. DEL) to run when stopping to ensure safe cleanup.
- Provides convenience methods with built-in retry for common queue and deduplication patterns.

**Usage**

`RedisManager` only needs two things to initialize:
1. An `asyncio.Event` (`stop_event`) — used for graceful shutdown.
2. A `redis_url` — connection string for Redis.

After that, it can be used exactly like a native `redis.asyncio.Redis` instance.

```python
import asyncio
from scrapy_cffi.databases import RedisManager

async def main():
    stop_event = asyncio.Event()
    redis = RedisManager(stop_event, "redis://localhost:6379/0")

    await redis.set("foo", "bar")
    val = await redis.get("foo")
    print(val)  # b"bar"

    # Graceful shutdown
    stop_event.set()

asyncio.run(main())
```

## 2.2 SQLAlchemyMySQLManager/MongoDBManager
Extended usage examples for MongoDB and MySQL can be found at:
1. MongoDB: https://github.com/aFunnyStrange/scrapy_cffi/blob/main/tests/test_mongodb.py
2. MySQL: https://github.com/aFunnyStrange/scrapy_cffi/blob/main/tests/test_mysql.py
