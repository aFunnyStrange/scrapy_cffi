# 1.Introduction
scrapy_cffi.databases provides adapter frameworks with automatic retry and reconnection utility classes for `Redis`, `MySQL`, `PostgreSQL`, and `MongoDB`. By default, `Redis` is included. For using the SQL or MongoDB utility classes, you need to install the dependencies manually:
```bash
pip install sqlalchemy[asyncio] aiomysql
pip install sqlalchemy[asyncio] asyncpg
pip install motor>=3.7.1
```

Optional PostgreSQL smoke test: `tests/test_postgres/test_postgres_manager.py` (requires running Postgres + `asyncpg`).

---



# 2.Usage
`RedisManager` and `MongoDBManager` support seamless use of their native APIs. `SQLAlchemyMySQLManager` and `SQLAlchemyPostgresManager` expose SQLAlchemy async `engine` and `session_factory`, plus small convenience helpers such as `execute`, `fetchone`, `fetchall`, and `run_stmt`.

Specifically, once connected, `RedisManager` provides **full compatibility with the native `redis.asyncio` API**.

Retry is implemented at explicit I/O boundaries, not by intercepting every
attribute access. Concurrent failures share one reconnect operation, so a
database outage does not make every spider task rebuild the same client or
pool. This also keeps public types visible to IDEs:

- `RedisManager` subclasses `redis.asyncio.Redis`; native commands such as
  `get`, `set`, Streams, pipelines, and scripts retain their normal completion.
- `MongoDBManager.collection()` is typed as `AsyncIOMotorCollection` while a
  small internal proxy refreshes the collection after reconnect.
- SQL managers expose typed `engine` and `session_factory` attributes, and use
  explicitly declared helpers instead of dynamic method wrapping.

## 2.1 RedisManager
An async Redis client extending `redis.asyncio.Redis` with full API support.

**Features:**
- Automatically retries and reconnects on connection failures.
- Respects a global asyncio stop event to gracefully abort operations during shutdown.
- Only allows certain Redis commands (e.g. DEL) to run when stopping to ensure safe cleanup.
- Provides convenience methods with built-in retry for common queue and deduplication patterns.
- Routes retry through Redis' common `execute_command` gateway; it does not
  cache or replace bound Redis methods.

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

### 2.1.1 Redis Stream ingress (RedisSpider)
For `RedisSpider` start URLs, the framework supports list (`BLPOP`) and Stream consumer-group (`XREADGROUP`) modes. Configuration can live on the spider **or** in `settings.REDIS_STREAM_INFO`; resolution is handled by `scrapy_cffi.databases.redis_ingress`.

Low-level helpers on `RedisManager`:
- `dequeue_stream_request(...)` — read one message from a consumer group
- `ack_stream_request(message, group_name)` — `XACK`

See [2-spiders.md](./2-spiders.md#22-redisspider) and [1-settings.md](./1-settings.md#293-redis_stream_info).

## 2.2 SQLAlchemyMySQLManager / SQLAlchemyPostgresManager
Only `execute`, `fetchone`, `fetchall`, and `run_stmt` are automatically
replayed after a retryable connection failure. Native `engine` /
`session_factory` usage remains fully explicit: transactions are never
silently replayed by an attribute proxy.

Both managers share `BaseSQLAlchemyManager` (retry, reconnect, pool). Configure connection and pool options via `MYSQL_INFO` / `POSTGRES_INFO` in settings — the crawler calls `init()` automatically when `resolved_url` is set.

```python
from scrapy_cffi.settings import SettingsInfo
from scrapy_cffi.models import PostgresInfo

settings = SettingsInfo()
settings.POSTGRES_INFO = PostgresInfo(
    HOST="127.0.0.1",
    PORT=5432,
    USERNAME="postgres",
    PASSWORD="secret",
    DB="app",
    ECHO=False,
    POOL_PRE_PING=True,
    POOL_SIZE=5,
    MAX_OVERFLOW=10,
)
# Or pass a full URL:
# settings.POSTGRES_INFO.URL = "postgresql+asyncpg://user:pass@localhost:5432/app"
```

In a spider or pipeline, use `crawler.postgresManager` / `crawler.mysqlManager` after startup. Both managers extend `BaseSQLAlchemyManager` (shared retry/reconnect/session helpers).

Extended usage examples:
1. MongoDB: https://github.com/aFunnyStrange/scrapy_cffi/blob/main/tests/test_mongodb.py
2. MySQL: https://github.com/aFunnyStrange/scrapy_cffi/blob/main/tests/test_mysql.py
3. PostgreSQL: https://github.com/aFunnyStrange/scrapy_cffi/blob/main/tests/test_postgres/test_postgres_manager.py

Standalone manager usage (PostgreSQL):

```python
from scrapy_cffi.databases.postgres import SQLAlchemyPostgresManager

manager = SQLAlchemyPostgresManager(stop_event, "postgresql+asyncpg://user:pass@localhost:5432/app")
await manager.init()
await manager.execute(
    "insert into items (name, price) values (:name, :price)",
    {"name": "demo", "price": 12},
)
row = await manager.fetchone("select * from items where name=:name", {"name": "demo"})
await manager.close()
```
