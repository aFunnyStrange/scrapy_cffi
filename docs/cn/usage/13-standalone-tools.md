# 不启动 Crawler 的直接使用

[English](../../en/usage/13-standalone-tools.md) | 简体中文

稳定的直接调用边界是 `build_resource_service`，不是已经移除的数据库/MQ Manager 模块。

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

该路径与真实 Crawler 使用相同配置、Repository、重试策略、资源替换和关闭行为。

## 分层导入

```python
# 一次性供应商传输，没有重试策略
from scrapy_cffi.infra.redis import RedisClient
from scrapy_cffi.infra.rabbitmq import RabbitMQClient
from scrapy_cffi.infra.kafka import KafkaClient

# 稳定持久化与队列语义
from scrapy_cffi.repo import RedisRepository, SQLRepository
from scrapy_cffi.repo.queue import RabbitMQQueueRepository, KafkaQueueRepository

# 生命周期与恢复能力
from scrapy_cffi.service import ResourceService, ResourceSlot, RetryPolicy
```

通常应由组合根构造 Infra Client；直接使用原生 Client 时，调用者自行承担一次性失败处理。

## 轻量工具与入口

```python
from scrapy_cffi.tools import canonical_request_url, SettingsInfo
from scrapy_cffi.utils.algorithm import do_sha1
from scrapy_cffi.utils.jsonLoad import extract_json_chain

from scrapy_cffi.config import RedisIngressMode, RedisStreamConsumerInfo
from scrapy_cffi.repo.redis_ingress import (
    RedisIngressConfig,
    dequeue_start_request,
    resolve_redis_ingress,
)
```

根包 Runner 为惰性导出，仅导入 `scrapy_cffi` 不会启动 Crawler：

```python
import scrapy_cffi

scrapy_cffi.run_all_spiders(settings)
scrapy_cffi.run_spiders_sync([...])
```

