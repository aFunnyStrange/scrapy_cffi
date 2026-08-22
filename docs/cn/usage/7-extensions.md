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

## 4. 框架内置但默认关闭的 Extension

新生成的项目默认不启用任何 Extension。没有监听者时 Signal 会立即丢弃，因此普通 Worker 不承担监控网络请求或 SMTP 开销。

`CrawlerMonitorExtension` 向可选 Hub 上报生命周期与错误事件。请求、响应、丢弃和 Item 等高频 Signal 只在本地计数，累计到 `MONITOR_INFO.EVENT_BATCH_SIZE` 后才上报。显式启用后，它会从第一个 Engine 启动到明确关闭期间持有一个低频心跳任务；心跳只影响 Hub 可用性，绝不参与 Crawler 完成判断。

```python
from scrapy_cffi.extensions import CrawlerMonitorExtension

settings.MONITOR_INFO.HUB_URL = "http://127.0.0.1:6800"
settings.MONITOR_INFO.HEARTBEAT_INTERVAL = 15.0
settings.EXTENSIONS_PATH = CrawlerMonitorExtension
```

`EmailNotificationExtension` 使用惰性 SMTP 连接和 `asyncio.to_thread()`。默认在 Engine 停止时发送汇总；只有设置 `EMAIL_INFO.SEND_ON_ERROR = True` 才会即时发送错误邮件。

```python
from scrapy_cffi.extensions import EmailNotificationExtension

settings.EMAIL_INFO.HOST = "smtp.example.com"
settings.EMAIL_INFO.USERNAME = "crawler@example.com"
settings.EMAIL_INFO.TO_ADDRESSES = ["ops@example.com"]
settings.EXTENSIONS_PATH = EmailNotificationExtension
```

密码应通过被 Git 忽略的 `.env` 中的 `EMAIL_INFO__PASSWORD` 提供。Server 与 Hub 模式见[可选爬虫监控控制台](17-monitoring.md)。
