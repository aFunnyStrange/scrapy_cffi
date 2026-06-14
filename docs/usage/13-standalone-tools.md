# Standalone tools (without the crawler)

`scrapy_cffi` can be used as a **tool library**: import `databases`, `mq`, `utils`, and `models` without starting a crawl loop.

> **Tip:** Prefer submodule imports below. Root `import scrapy_cffi` only loads `runner` APIs on demand (lazy); it does not import `Crawler` until you access `run_spider` and friends.

## Installation

Same package as the framework:

```bash
pip install scrapy_cffi
# or latest main:
python -m pip install "scrapy_cffi @ git+https://github.com/aFunnyStrange/scrapy_cffi.git"
```

Optional extras: `scrapy_cffi[media]` for MIME helpers (`filetype`); tool namespace: `scrapy_cffi.tools` (lazy).

---

## Tier-0: databases

### Redis

```python
import asyncio
from scrapy_cffi.databases import RedisManager
from scrapy_cffi.models import RedisInfo

async def main():
    stop = asyncio.Event()
    # Direct URL
    redis = RedisManager(stop, "redis://127.0.0.1:6379/0")
    await redis.set("k", "v")

    # Or from config model
    info = RedisInfo(HOST="127.0.0.1", PORT=6379, DB=0)
    redis = RedisManager.from_redis_info(stop, info)

asyncio.run(main())
```

### PostgreSQL / MySQL (SQLAlchemy async)

```python
import asyncio
from scrapy_cffi.databases.postgres import SQLAlchemyPostgresManager
from scrapy_cffi.models import PostgresInfo

async def main():
    stop = asyncio.Event()
    info = PostgresInfo(
        HOST="127.0.0.1", PORT=5432, USERNAME="postgres", PASSWORD="secret", DB="app"
    )
    db = SQLAlchemyPostgresManager.from_db_info(stop, info)
    await db.init()
    await db.execute("select 1")
    await db.close()

asyncio.run(main())
```

MySQL: `SQLAlchemyMySQLManager.from_db_info(stop, MysqlInfo(...))`.

### MongoDB

```python
from scrapy_cffi.databases.mongodb import MongoDBManager
from scrapy_cffi.models import MongodbInfo

info = MongodbInfo(HOST="127.0.0.1", PORT=27017, DB="app")
mongo = MongoDBManager.from_mongodb_info(asyncio.Event(), info)
```

### Redis Stream ingress (RedisSpider helpers)

```python
from scrapy_cffi.databases.redis_ingress import (
    RedisIngressConfig,
    resolve_redis_ingress,
    dequeue_start_request,
)
from scrapy_cffi.models import RedisStreamConsumerInfo, RedisIngressMode
```

See [14-multi-spider-resources.md](./14-multi-spider-resources.md) for key ownership.

---

## Tier-0: message queues

```python
import asyncio
from scrapy_cffi.mq import RabbitMQManager, KafkaManager
from scrapy_cffi.models import RabbitMQInfo, KafkaInfo

stop = asyncio.Event()
rabbit = RabbitMQManager.from_rabbitmq_info(stop, RabbitMQInfo(URL="amqp://guest:guest@127.0.0.1:5672/"))
kafka = KafkaManager.from_kafka_info(stop, KafkaInfo(URL="127.0.0.1:9092"))
```

Framework path (equivalent):

```python
RabbitMQManager.from_crawler(crawler)
```

---

## Tier-0: utils (lazy barrel + submodules)

**Recommended** — import the submodule you need:

```python
from scrapy_cffi.utils.algorithm import do_sha1
from scrapy_cffi.utils.jsonLoad import extract_json_chain
from scrapy_cffi.utils.media import guess_content_type  # pip install scrapy_cffi[media]
from scrapy_cffi.utils.envConfig import settings_to_env, env_to_settings
from scrapy_cffi.utils.fd import FDUtil
```

Legacy barrel (lazy, one symbol → one submodule load):

```python
from scrapy_cffi.utils import extract_json_chain  # OK; does not eager-import robot/jsonLoad/...
```

Avoid when you only need one helper:

```python
from scrapy_cffi.utils import RobotsManager  # pulls utils.robot (framework-oriented)
```

Media optional extra: `pip install scrapy_cffi[media]` (`filetype`, `Pillow`, `hachoir`) — replaces old `[windows]` / `[unix]` magic extras.

---

## Factory cheat sheet

| Component | Standalone factory | Framework |
| --------- | ------------------ | --------- |
| Redis | `RedisManager.from_redis_info(stop, info)` | `from_crawler(crawler)` |
| MySQL / Postgres | `*.from_db_info(stop, info)` | `from_crawler(crawler)` |
| MongoDB | `from_mongodb_info(stop, info)` | `from_crawler(crawler)` |
| RabbitMQ | `from_rabbitmq_info(stop, info, persist=…)` | `from_crawler(crawler)` |
| Kafka | `from_kafka_info(stop, info)` | `from_crawler(crawler)` |

All factories accept `asyncio.Event` as `stop_event` for graceful shutdown.

Optional single namespace (lazy): `from scrapy_cffi.tools import RedisManager, canonical_request_url` — see [13-standalone-tools.md](./13-standalone-tools.md).

---

## Framework runner (lazy root API)

```python
import scrapy_cffi

# Loaded on first access — does not import Crawler at import time
scrapy_cffi.run_all_spiders(settings)
scrapy_cffi.run_spiders([scrapy_cffi.SpiderRunConfig(settings=a), ...])
scrapy_cffi.run_spiders_sync([...])  # blocking multi-Crawler
```

See [6-run.md](./6-run.md) and [ARCHITECTURE-ROADMAP.md](../ARCHITECTURE-ROADMAP.md).
