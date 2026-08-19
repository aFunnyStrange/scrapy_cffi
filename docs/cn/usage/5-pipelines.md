# Item Pipeline

[English](../../en/usage/5-pipelines.md) | 简体中文

Pipeline 保留 Scrapy 风格的异步生命周期钩子，并通过稳定契约获得框架服务。

| 属性 | 说明 |
| --- | --- |
| `settings` | 当前 Crawler 已验证的 `SettingsInfo` |
| `logger` | 框架 Logger |
| `resources` | 带类型的 `ResourceService`，可能提供 Redis、MySQL、PostgreSQL、MongoDB、RabbitMQ、Kafka Repository |
| `hooks` | 面向 Pipeline 的 Session 与 Signal Hook |

0.4 已移除六个旧 `*Manager` 属性。Repository 提供稳定持久化和队列语义；客户端生命周期、有界重试和替换统一由 `ResourceService` 管理。

```python
from scrapy_cffi.pipelines import Pipeline

class SavePipeline(Pipeline):
    async def process_item(self, item, spider):
        postgres = self.resources.postgres
        if postgres is None:
            raise RuntimeError("POSTGRES_INFO is not configured")
        await postgres.execute(
            "insert into items(name) values (:name)",
            {"name": item["name"]},
        )
        return item
```

只有在有意执行供应商原生一次性操作时才使用 `repository.client`、`engine` 或 `session_factory`；这些逃生口不会被框架静默重放。

## 生命周期

- `open_spider(spider)`：Spider 打开后调用，此时基础设施已经启动，可进行 Pipeline 专属准备。
- `process_item(item, spider)`：接收回调产生的每个 Item，可校验、转换、持久化或丢弃。
- `close_spider(spider)`：Spider 关闭时调用。共享资源会在全部 Engine 停止后统一关闭，单个 Pipeline 不得关闭 `self.resources`。

`run_all_spiders` 中多个 Spider 共用一个 ResourceService，所有计划工作完成后一起关闭共享资源。

