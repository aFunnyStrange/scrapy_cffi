# Optional worker monitoring console

[Documentation home](../README.md) | [简体中文](../../cn/usage/17-monitoring.md)

The Hub is an experimental observation process for worker instances and
framework runs. It is not a scheduler, durable task source of truth, retry
manager, or restart manager. MySQL/Postgres task state remains owned by the
application manager or an external scheduler.

## State ownership

The Hub deliberately separates three facts:

- application tasks such as `pending`, `retry`, and `completed` belong to the
  application database and scheduler;
- framework runs report `running`, `completed`, `failed`, or `cancelled`;
- worker availability reports `online` or `unreachable`.

A missing heartbeat can change only availability to `unreachable`. It never
invents a failed, stopped, or completed lifecycle transition.

## Installation and binding

FastAPI and Uvicorn remain optional:

```bash
pip install "scrapy_cffi[server]"
scrapy-cffi server
# http://127.0.0.1:6800
```

Trusted remote workers can use `scrapy-cffi server --hub --port 6800`. The
built-in command has no authentication and uses an in-memory observation
store. Bind `0.0.0.0` only on a trusted network or behind an authenticated
reverse proxy.

## Enabling observations

Monitoring is never enabled implicitly:

```python
from scrapy_cffi.extensions import CrawlerMonitorExtension

settings.MONITOR_INFO.HUB_URL = "http://hub.internal:6800"
settings.MONITOR_INFO.WORKER_ID = "orders-worker"
settings.MONITOR_INFO.EVENT_BATCH_SIZE = 100
settings.MONITOR_INFO.HEARTBEAT_INTERVAL = 15.0
settings.EXTENSIONS_PATH = CrawlerMonitorExtension
```

The extension creates its heartbeat task only after the first Engine starts,
retains it, and cancels it during explicit run shutdown. Hot counters remain
batched. Hub outages are logged without failing crawler work.

Each event carries `worker_id`, process `instance_id`, invocation `run_id`, an
optional external `task_id`, and an ordered sequence. Pass scheduler identity
with the public run API:

```python
from scrapy_cffi import RunContext, start_spider_run

context = RunContext.create(task_id=database_task_id, attempt=2)
handle = await start_spider_run(settings, run_context=context)
outcome = await handle.wait()

# The application maps outcome.state to its own durable task transitions.
await task_repository.apply_outcome(database_task_id, outcome)
```

Existing `run_spider()` callers remain supported and still receive
`(crawler, engine_task)`.

## Replaceable stores and durable task views

`create_monitor_app()` accepts an `ObservationStore` and an optional read-only
`TaskStateProvider`. The provider maps an existing application schema to
`TaskSnapshot`; the Hub never writes that schema.

```python
app = create_monitor_app(
    store=project_observation_store,
    task_state_provider=project_task_provider,
)
```

The JSON API exposes:

- `GET /api/v1/workers` for worker lifecycle and availability;
- `GET /api/v1/runs` for framework execution state;
- `GET /api/v1/tasks` and `/api/v1/tasks/{task_id}` for an optional durable
  task provider;
- `POST /api/v1/workers/events` for observation ingestion.

Run a custom application factory with Uvicorn when project-specific stores or
providers are required. The convenience `scrapy-cffi server` command keeps the
dependency-free in-memory defaults.
