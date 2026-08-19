# 多 Spider 资源归属

[English](../../en/usage/14-multi-spider-resources.md) | 简体中文

## 模式 A：一个 Crawler，共享基础 SettingsInfo

`run_all_spiders` 为每个 Spider 创建独立 Scheduler。普通 `Spider` 保留内存 Scheduler；同组存在 Redis、RabbitMQ 或 Kafka Spider 不会导致隐式提升。只有显式全局 `settings.SCHEDULER` 才统一覆盖 Scheduler 类型。

| 资源 | 作用域 | 隔离方式 |
| --- | --- | --- |
| Memory/Redis 工作队列 | 每 Spider | `scheduler_queue_key` / `queue_name`，否则由 `QUEUE_NAME` 与 Spider 名生成 |
| Redis 去重 | 每 Spider | Scheduler 自动设置 `redis_namespace = spider.name` |
| Redis List/Stream 启动入口 | 每 Spider | `redis_key` 或 `REDIS_STREAM_INFO` |
| Stream Consumer Group | 每 Spider/项目 | `redis_group`、`GROUP_NAME` |
| 内存去重 | 每 Scheduler | 独立 `MemoryDupeFilter` 实例 |
| `SettingsInfo` 覆盖 | 每 Spider | Spider 类 `settings_overlay` |
| ResourceService 与连接池 | 每 Crawler 共享 | 同一套连接配置 |
| Session、Downloader | 每 Crawler 共享 | 同一事件循环和全局并发边界 |

```python
from scrapy_cffi.spiders import RedisSpider

class WorkerA(RedisSpider):
    name = "worker_a"
    scheduler_queue_key = "proj:worker_a:req"
    redis_key = "proj:worker_a:start"
    settings_overlay = {"MAX_CONCURRENT_REQ": 20}

class WorkerB(RedisSpider):
    name = "worker_b"
    scheduler_queue_key = "proj:worker_b:req"
    redis_key = "proj:worker_b:start"
    settings_overlay = {"MAX_CONCURRENT_REQ": 5}
```

Redis Stream 入口解析顺序为：Spider 属性 → `REDIS_STREAM_INFO` → `{name}_redis_start`。

## 模式 B：`run_spiders`，一个循环多个 Crawler

每个 `SpiderRunConfig` 持有自己的 `SettingsInfo`、资源服务和连接：

```python
import scrapy_cffi

scrapy_cffi.run_spiders_sync([
    scrapy_cffi.SpiderRunConfig(settings=base_a, start_type=1),
    scrapy_cffi.SpiderRunConfig(settings=base_b, start_type=1),
])

# 异步环境：
# crawlers, tasks = await scrapy_cffi.run_spiders([...])
# await asyncio.gather(*tasks)
```

## 模式 C：每个 Spider 一个事件循环

```python
import threading
import scrapy_cffi

def run_in_thread(settings):
    scrapy_cffi.run_spider_sync(settings, new_loop=True)

threading.Thread(target=run_in_thread, args=(settings_a,)).start()
threading.Thread(target=run_in_thread, args=(settings_b,)).start()
```

需要完整进程隔离时使用 `multiprocessing` 与 `run_spider_sync(..., new_loop=True)`。不要跨循环共享 asyncio 对象。

相关文档：[Spider](2-spiders.md)、[配置](1-settings.md)、[独立工具](13-standalone-tools.md)、[去重](15-deduplication.md)。

