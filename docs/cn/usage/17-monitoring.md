# 可选爬虫监控控制台

[文档首页](../README.md) | [English](../../en/usage/17-monitoring.md)

监控控制台是面向当前成熟 Crawler Worker 的实验性观测进程。它不是调度器、任务状态真相源、自动重启管理器或持久化指标数据库。其他 Worker 类型只有出现真实生命周期需求后，才会加入统一观测协议。

## 安装与监听地址

FastAPI 与 Uvicorn 是可选依赖，框架核心导入时不会加载它们：

```bash
pip install "scrapy_cffi[server]"
```

本地模式默认只监听回环地址：

```bash
scrapy-cffi server
# http://127.0.0.1:6800
```

显式 Hub 模式监听所有网卡，允许远程爬虫进程注册：

```bash
scrapy-cffi server --hub --port 6800
# http://0.0.0.0:6800
```

当前 Hub 没有认证并且只在内存保存状态。只有在可信网络或带认证的反向代理之后才能绑定 `0.0.0.0`；Hub 重启后观测记录会清空。

## 为 Crawler 启用监控

监控永远不会被框架隐式启用。在生成项目的 `settings.py` 中显式注册：

```python
from scrapy_cffi.extensions import CrawlerMonitorExtension

settings.MONITOR_INFO.HUB_URL = "http://hub.internal:6800"
settings.MONITOR_INFO.WORKER_ID = "orders-worker-1"
settings.MONITOR_INFO.EVENT_BATCH_SIZE = 100
settings.EXTENSIONS_PATH = CrawlerMonitorExtension
```

生命周期与错误立即上报；请求、响应和 Item 等高频事件按批聚合。Hub 不可用只会记录警告，不会让爬虫任务失败。页面通过 `GET /api/v1/workers` 轮询，Extension 通过 `POST /api/v1/workers/events` 上报。
