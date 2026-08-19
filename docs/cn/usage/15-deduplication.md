# 去重架构

[English](../../en/usage/15-deduplication.md) | 简体中文

## 组件职责

| 组件 | 职责 |
| --- | --- |
| Fingerprint | 规范 URL 与选定 Header 后计算 SHA1，不访问 Redis |
| `MemoryDupeFilter` / `BloomDupeFilter` | 本地 Scheduler 的进程内去重 |
| `RedisDupeFilter` | Redis SET + Lua 去重 |
| `RedisBloomDupeFilter` | Redis Bitmap Bloom，内存更低但有小概率误判 |
| `DedupKeyRouter` | 把指纹映射到 `new_seen`、`sent_seen` 键 |

## Cluster Jump Hash

Redis Cluster 按 Hash Slot 路由。`DedupKeyRouter` 对启动节点使用 Jump Consistent Hash，并在键名后加入 `:{host:port}`：它只提供同一 URL 的键亲和性，不负责 Crawler 负载均衡，也不替代 Redis Cluster 自身路由。Crawler 仍只面向一个 Cluster-aware `RedisRepository`。

多数团队直接使用单机 Redis 或 Sentinel 同时承担队列和去重。共享大规模 Cluster 时保留 Jump Hash Router，并通过配置控制。除非确实需要跨语言客户端或集中策略，不要再增加 HTTP/gRPC 去重微服务——Redis 已经是分布式去重服务。

## 配置

```python
settings.REDIS_INFO.CLUSTER_NODES = [
    "redis-cluster-01.internal:6379",
    "redis-cluster-02.internal:6379",
    "redis-cluster-03.internal:6379",
]
settings.FILTER_KEY = "myproject"
settings.DEDUP_TTL = 86400
settings.DUPEFILTER = "scrapy_cffi.dupefilter.api.RedisDupeFilter"
```

Bloom 使用版本化 `xxh3-km-v1`：两个 XXH3 Hash 加 Kirsch-Mitzenmacher Double Hashing。安装 `scrapy_cffi[bloom]` 使用 `fastbloom-rs` PyO3 stable-ABI 后端；纯 Python `ppxxh` 回退产生完全相同的索引。Redis Bitmap 键包含算法版本，旧 FNV 键不会被新算法误读。

## 关闭清理

`SCHEDULER_PERSIST=False` 时，`Crawler.shutdown()` 删除：

- Spider 入口键和分布式工作队列；
- 每个 Spider 拥有的 RabbitMQ/Kafka 启动与工作队列/Topic；
- `RedisDupeFilter.dedup_cleanup_keys()` 返回的去重键。

清理在正常退出和 Ctrl+C 都执行。Redis 清理与 Broker 清理独立启动，某个 Broker 失败不能阻止 Redis 清理；失败后端会再重试一次。Cluster 模式会清理所有已知启动节点后缀，但节点变化仍可能残留，因此应设置 `DEDUP_TTL` 作为安全网。

入口请求与 `start_urls` 带 `meta["is_start_url"]`，在 Redis/RabbitMQ Scheduler 中绕过去重。

## 独立使用

```python
from scrapy_cffi.dupefilter.routing import DedupKeyRouter

router = DedupKeyRouter.from_redis_repository(
    settings,
    resources.redis,
    namespace="spider_a",
)
keys = router.for_fingerprint("abc123fingerprint...")
```

相关文档：[多 Spider 资源](14-multi-spider-resources.md)、[独立工具](13-standalone-tools.md)、[架构路线图](../ARCHITECTURE-ROADMAP.md)。
