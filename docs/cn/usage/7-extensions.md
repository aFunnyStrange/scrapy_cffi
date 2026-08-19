# 1. Extension 与 Signal

[English](../../en/usage/7-extensions.md) | 简体中文

Signal 系统允许 Extension 在框架核心之外观察事件。所有载荷统一使用 `SignalInfo`。没有启用 Extension 时框架仍会产生内部 Signal，但会立即丢弃。

Signal 是异步广播，只适合扩展和观测，不能承担严格时序控制。`signal_time` 可用于下游分析。持续队列 Spider 只有在显式中断时退出，关闭期间仍未处理的观测 Signal 可以丢弃，但框架拥有的资源必须正常关闭。

## 2. 常用 Signal

- 核心：`engine_started`、`engine_stopped`、`scheduler_empty`、`task_error`；
- Spider：`spider_opened`、`spider_closed`、`spider_error`；
- 调度：`request_scheduled`、`request_dropped`；
- Downloader：`request_reached_downloader`、`response_received`；
- Item：`item_scraped`、`item_dropped`、`item_error`。

`item_dropped` 与 `item_error` 不由框架自动发送，因为是否丢弃或失败取决于用户 Pipeline；需要时通过 Hook 主动发送。

## 3. 注册 Extension

```python
from scrapy_cffi.extensions import Extension, signals

class CustomExtension(Extension):
    @classmethod
    def from_crawler(cls, hooks, resources):
        instance = cls(hooks=hooks, resources=resources)
        hooks.signals.connect(signals.engine_started, instance.on_started)
        return instance

    async def on_started(self, info):
        ...
```

生成 Demo 包含可运行示例：

```bash
scrapy-cffi demo
```

