# 数据库架构

[English](../../en/usage/8-databases.md) | 简体中文

数据库能力遵循单向依赖：

```text
Crawler / Pipeline / Spider
  -> ResourceService
  -> Repository
  -> Infra Client
  -> Vendor Driver
```

`infra` 管理一次性供应商客户端与连接池，`repo` 管理存储语义，`service` 管理生命周期、有界重试和客户端替换，`build_resource_service()` 是 Crawler 与直接测试共用的组合根。具体客户端不得持有 Crawler 状态、停止事件、重试循环或重连控制器。

## 安装

Redis 属于核心依赖，其他数据库按需安装：

```bash
pip install "scrapy_cffi[mysql]"
pip install "scrapy_cffi[postgres]"
pip install "scrapy_cffi[mongodb]"
```

## 框架内使用

Spider、Pipeline 与 Extension 都获得同一个 `resources` 服务。可用 Repository 为 `redis`、`mysql`、`postgres`、`mongodb`、`rabbitmq`、`kafka`；未配置时值为 `None`。

```python
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

## 直接调用与测试

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
        print(await resources.postgres.fetchone("select 1"))
    finally:
        await resources.close()

asyncio.run(main())
```

这是推荐的功能测试边界：测试可替换 Infra Factory，同时运行真实 Repository 与 Service 行为。

## Repository 约定

- `RedisRepository` 提供队列、Stream、分布式去重与 Session Hash。`.client` 暴露原生客户端，但调用是一次性的，不会自动重放。
- `SQLRepository` 提供 `execute`、`fetchone`、`fetchall`、`run_stmt`。`.engine` 和 `.session_factory` 供应用显式控制原生事务；框架不会重放任意事务。错误凭据或数据库不存在等致命配置错误不重试。
- `MongoRepository` 提供 `list_collections`、`drop_database`；`collection(name)` 返回原生 Motor Collection。

```python
settings.INFRA_RETRY_ATTEMPTS = 3
settings.INFRA_RETRY_DELAY = 1.0
```

同一客户端代际的并发失败共享一次 `ResourceSlot` 替换。`asyncio.CancelledError` 必须传播，资源关闭统一由 `ResourceService.close()` 完成。

