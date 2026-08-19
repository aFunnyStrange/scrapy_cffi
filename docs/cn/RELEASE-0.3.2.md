# scrapy_cffi 0.3.2：去重清理、C 扩展与 Demo 稳定性

[English](../en/RELEASE-0.3.2.md) | 简体中文

## 主要变化

- `SCHEDULER_PERSIST = False` 时，正常退出或 Ctrl+C 会通过 `DedupKeyRouter.cleanup_keys()` 删除入口队列、工作队列和 `cffiFilter_*` 去重键。
- 每个 Spider 使用自己的 Redis 去重命名空间，如 `cffiFilter_new_seen:<spider.name>`；入口任务和 `start_urls` 不参与该阶段去重。
- `scrapy-cffi cinstall` 可把本地构建的 Bloom 或其他 ctypes 二进制安装到用户系统存储。
- `allowed_domains` 按主机名匹配，`127.0.0.1` 可以匹配任意端口。

| 配置 | 行为 |
| --- | --- |
| `SCHEDULER_PERSIST = False` | 关闭时删除 Redis 入口、队列与去重键 |
| `SCHEDULER_PERSIST = True` | 跨运行保留键 |
| `DEDUP_TTL > 0` | 让去重键自动过期 |
| `redis_namespace` | Scheduler 自动设置的每 Spider 命名空间 |

PyPI wheel 只包含 Python 包装与纯 Python 回退，不携带平台相关 `.dll` 或 `.so`：

```bash
scrapy-cffi startproject myproj
scrapy-cffi cinstall --init bloom
scrapy-cffi cinstall bloom --require-binary
scrapy-cffi cinstall --list
```

详见 [CPython 扩展](usage/12-cpython.md) 与 [去重架构](usage/15-deduplication.md)。

