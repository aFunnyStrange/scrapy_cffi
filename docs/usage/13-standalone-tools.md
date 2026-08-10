# Direct use without starting a crawler

The stable direct-use boundary is `build_resource_service`, not the removed database/MQ Manager modules.

```python
import asyncio

from scrapy_cffi import build_resource_service
from scrapy_cffi.config import RedisInfo
from scrapy_cffi.settings import SettingsInfo


async def main():
    settings = SettingsInfo(
        REDIS_INFO=RedisInfo(URL="redis://127.0.0.1:6379/0")
    )
    resources = build_resource_service(settings, asyncio.Event())
    await resources.start()
    try:
        await resources.redis.rpush("requests", b"payload")
    finally:
        await resources.close()


asyncio.run(main())
```

This path exercises the same configuration, repositories, retry policy, resource replacement, and shutdown behavior as a real crawler.

## Layer-specific imports

Use these only when intentionally testing or extending one layer:

```python
# One-shot vendor transports; no retry policy.
from scrapy_cffi.infra.redis import RedisClient
from scrapy_cffi.infra.rabbitmq import RabbitMQClient
from scrapy_cffi.infra.kafka import KafkaClient

# Stable persistence and queue semantics.
from scrapy_cffi.repo import RedisRepository, SQLRepository
from scrapy_cffi.repo.queue import RabbitMQQueueRepository, KafkaQueueRepository

# Lifecycle and resilience extensions.
from scrapy_cffi.service import ResourceService, ResourceSlot, RetryPolicy
```

Infrastructure clients should normally be constructed by the composition root. If an extension uses a native client directly, that call is one-shot and the extension owns its failure handling.

## Lightweight tools

`scrapy_cffi.tools` now contains only helpers that do not construct external infrastructure:

```python
from scrapy_cffi.tools import canonical_request_url, SettingsInfo
from scrapy_cffi.utils.algorithm import do_sha1
from scrapy_cffi.utils.jsonLoad import extract_json_chain
```

Typed `TYPE_CHECKING` imports keep IDE navigation available while optional runtime dependencies remain lazy.

## Redis Stream ingress helpers

```python
from scrapy_cffi.config import RedisIngressMode, RedisStreamConsumerInfo
from scrapy_cffi.repo.redis_ingress import (
    RedisIngressConfig,
    dequeue_start_request,
    resolve_redis_ingress,
)
```

## Framework runner

```python
import scrapy_cffi

scrapy_cffi.run_all_spiders(settings)
scrapy_cffi.run_spiders_sync([...])
```

Root runner exports remain lazy and do not start a crawler merely by importing the package.
