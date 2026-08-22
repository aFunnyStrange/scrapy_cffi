# Optional crawler monitoring console

[Documentation home](../README.md) | [简体中文](../../cn/usage/17-monitoring.md)

The monitoring console is an experimental observation process for the mature
Crawler Worker. It is not a scheduler, task source of truth, restart manager,
or durable metrics database. Other Worker types will join the wire contract
only after their real lifecycle requirements exist.

## Installation and binding

FastAPI and Uvicorn are optional and are not imported by the framework core:

```bash
pip install "scrapy_cffi[server]"
```

Local mode binds only loopback:

```bash
scrapy-cffi server
# http://127.0.0.1:6800
```

Hub mode explicitly binds every interface so remote crawler processes can
register:

```bash
scrapy-cffi server --hub --port 6800
# http://0.0.0.0:6800
```

The initial Hub has no authentication and stores state only in memory. Bind
`0.0.0.0` only on a trusted network or behind an authenticated reverse proxy.
Restarting the process clears its observations.

## Enabling a crawler

Monitoring is never enabled implicitly. Add the Extension in the generated
project `settings.py`:

```python
from scrapy_cffi.extensions import CrawlerMonitorExtension

settings.MONITOR_INFO.HUB_URL = "http://hub.internal:6800"
settings.MONITOR_INFO.WORKER_ID = "orders-worker-1"
settings.MONITOR_INFO.EVENT_BATCH_SIZE = 100
settings.EXTENSIONS_PATH = CrawlerMonitorExtension
```

Lifecycle and error events are sent immediately. Hot request/response/item
events are aggregated and sent in batches. Hub unavailability is logged and
does not fail crawler work. The dashboard polls `GET /api/v1/workers`; crawler
extensions publish to `POST /api/v1/workers/events`.
