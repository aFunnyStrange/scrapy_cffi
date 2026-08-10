# Database architecture

Database support follows one dependency direction:

```text
Crawler / Pipeline / Spider
  -> ResourceService
  -> repository
  -> infra client
  -> vendor driver
```

- `scrapy_cffi.infra` owns one-shot vendor clients and connection pools.
- `scrapy_cffi.repo` owns Redis queue/dedup/session semantics and SQL/Mongo persistence operations.
- `scrapy_cffi.service` owns lifecycle, bounded retry, and client replacement.
- `scrapy_cffi.composition.build_resource_service()` is the composition root used by `Crawler` and direct tests.

Concrete clients do not contain crawler state, stop events, decorators, retry loops, or reconnect controllers.

## Installation

Redis is part of the core dependency set. Other databases are optional:

```bash
pip install "scrapy_cffi[mysql]"
pip install "scrapy_cffi[postgres]"
pip install "scrapy_cffi[mongodb]"
```

## Framework use

Spiders, pipelines, and extensions receive one typed `resources` service:

```python
from scrapy_cffi.pipelines import Pipeline


class SavePipeline(Pipeline):
    async def process_item(self, item, spider):
        if self.resources.postgres is None:
            raise RuntimeError("POSTGRES_INFO is not configured")
        await self.resources.postgres.execute(
            "insert into items(name) values (:name)",
            {"name": item["name"]},
        )
        return item
```

Available repositories are `resources.redis`, `mysql`, `postgres`, `mongodb`, `rabbitmq`, and `kafka`. An unconfigured resource is `None`.

## Direct and test use

Use the same composition path without starting a crawler:

```python
import asyncio

from scrapy_cffi import build_resource_service
from scrapy_cffi.config import PostgresInfo
from scrapy_cffi.settings import SettingsInfo


async def main():
    settings = SettingsInfo(
        POSTGRES_INFO=PostgresInfo(
            URL="postgresql+asyncpg://postgres:123456@127.0.0.1:5432/app"
        )
    )
    resources = build_resource_service(settings, asyncio.Event())
    await resources.start()
    try:
        if resources.postgres is None:
            raise RuntimeError("POSTGRES_INFO is not configured")
        row = await resources.postgres.fetchone("select 1")
        print(row)
    finally:
        await resources.close()


asyncio.run(main())
```

This is the recommended functional-test boundary: tests may replace infra factories while exercising the real repository and service behavior.

## Redis

`RedisRepository` provides the scheduler operations used for queues, Streams, distributed deduplication, and session hashes. Its `client` property deliberately exposes the current native `RedisClient` for advanced Redis commands:

```python
redis_repo = resources.redis
if redis_repo is None:
    raise RuntimeError("REDIS_INFO is not configured")
await redis_repo.client.set("custom:key", b"value")
```

Calls through explicit repository methods receive bounded retry and resource replacement. Calls made directly through `.client` are intentionally one-shot and are never replayed by the framework.

Redis single-node, Sentinel, and Cluster topology is configured with `scrapy_cffi.config.RedisInfo`. Stream ingress resolution lives in `scrapy_cffi.repo.redis_ingress`.

## SQLAlchemy

`SQLRepository` exposes `execute`, `fetchone`, `fetchall`, and `run_stmt`. These explicit operations may be retried after a retryable connection failure. The repository also exposes the current `engine` and `session_factory`; framework code never silently replays a user-controlled native transaction.

MySQL and PostgreSQL fatal configuration errors, such as invalid credentials or a missing database, are not retried.

## MongoDB

`MongoRepository` provides `list_collections` and `drop_database` with bounded recovery. `collection(name)` returns the native Motor collection for IDE completion and explicit application-controlled operations.

## Retry settings

```python
settings.INFRA_RETRY_ATTEMPTS = 3
settings.INFRA_RETRY_DELAY = 1.0
```

Concurrent failures from the same client generation share one `ResourceSlot` replacement. `asyncio.CancelledError` is always propagated, and normal resource shutdown remains centralized in `ResourceService.close()`.
