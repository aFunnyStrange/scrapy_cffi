# 可选 Worker 监控控制台

[文档首页](../README.md) | [English](../../en/usage/17-monitoring.md)

Hub 是面向 Worker 实例与框架单次运行的实验性观测进程。它不是调度器、持久化任务真相源、重试管理器或重启管理器。MySQL/Postgres 中的业务任务状态仍由用户的 manager 或外部调度层负责。

## 状态所有权

Hub 明确区分三类事实：

- `pending/retry/completed` 等业务任务状态属于用户数据库与调度层；
- 框架 Run 只报告 `running/completed/failed/cancelled`；
- Worker 可用性只报告 `online/unreachable`。

心跳缺失只能令可用性变成 `unreachable`，绝不能据此伪造 `failed`、`stopped` 或 `completed` 生命周期。

## 安装与监听地址

FastAPI 与 Uvicorn 仍然是可选依赖：

```bash
pip install "scrapy_cffi[server]"
scrapy-cffi server
# http://127.0.0.1:6800
```

可信远程 Worker 可以使用 `scrapy-cffi server --hub --port 6800`。内置命令没有认证，并使用内存观测 Store。只有在可信网络或带认证的反向代理之后才能绑定 `0.0.0.0`。

## 启用观测

监控永远不会被隐式启用：

```python
from scrapy_cffi.extensions import CrawlerMonitorExtension

settings.MONITOR_INFO.HUB_URL = "http://hub.internal:6800"
settings.MONITOR_INFO.WORKER_ID = "orders-worker"
settings.MONITOR_INFO.EVENT_BATCH_SIZE = 100
settings.MONITOR_INFO.HEARTBEAT_INTERVAL = 15.0
settings.EXTENSIONS_PATH = CrawlerMonitorExtension
```

Extension 只在第一个 Engine 启动后创建并持有心跳任务，并在显式关闭时取消它。高频计数仍然按批上报；Hub 不可用只记录警告，不会令爬虫失败。

每个事件包含 `worker_id`、进程级 `instance_id`、本次调用的 `run_id`、可选外部 `task_id` 和有序序号。外部调度层可以通过公共运行 API 传入关联信息：

```python
from scrapy_cffi import RunContext, start_spider_run

context = RunContext.create(task_id=database_task_id, attempt=2)
handle = await start_spider_run(settings, run_context=context)
outcome = await handle.wait()

# 业务层自行把 outcome.state 映射为持久化任务状态。
await task_repository.apply_outcome(database_task_id, outcome)
```

原有 `run_spider()` 调用仍兼容，继续返回 `(crawler, engine_task)`。

## 可替换 Store 与持久化任务视图

`create_monitor_app()` 接受 `ObservationStore` 和可选的只读 `TaskStateProvider`。Provider 负责把用户既有数据库结构映射为 `TaskSnapshot`；Hub 永远不会写入用户业务表。

```python
app = create_monitor_app(
    store=project_observation_store,
    task_state_provider=project_task_provider,
)
```

JSON API 包含：

- `GET /api/v1/workers`：Worker 生命周期和可用性；
- `GET /api/v1/runs`：框架运行状态；
- `GET /api/v1/tasks` 与 `/api/v1/tasks/{task_id}`：可选的持久化任务 Provider；
- `POST /api/v1/workers/events`：接收运行观测事件。

项目需要自定义 Store 或 Provider 时，应使用 Uvicorn 启动自己的应用工厂。便捷的 `scrapy-cffi server` 命令继续使用无额外数据库依赖的内存默认实现。
