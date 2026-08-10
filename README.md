## scrapy_cffi

> An asyncio-style web scraping framework inspired by Scrapy, powered by `curl_cffi`.

Requires Python 3.9 or newer. The framework uses `asyncio.to_thread` directly;
type annotations remain compatible with Python 3.9 and avoid the Python
3.10-only `X | Y` union syntax.

`scrapy_cffi` is a lightweight Python crawler framework that mimics the Scrapy architecture while replacing Twisted with `curl_cffi` as the underlying HTTP/WebSocket client. 

It is designed to be efficient, modular, and suitable for both simple tasks and large-scale distributed crawlers.

---

## ✨ Features

- **Scrapy-style architecture**: spiders, items, interceptors, pipelines, signals

- **Fully asyncio-based engine** for maximum concurrency

- **Stable HTTP platform**: injectable async Protocols with curl_cffi
  0.7.4-0.15 compatibility, WebSocket normalization, streaming, and SSE

- **Layered resource architecture**: parallel Redis, RabbitMQ, Kafka,
  SQLAlchemy, and MongoDB infra clients; stable repositories; and one typed
  service that owns lifecycle and bounded client replacement

- **Message queue scheduling**: Redis, RabbitMQ, and Kafka capabilities behind
  repository Protocols (separate Kafka start/work topics with manual acknowledgement)

- **Configurable deployment**: settings system supporting `.env`, single-instance, **sentinel**, and **cluster** mode

- **`scrapy-cffi infra`**: generate and manage independent project-local Docker infrastructure for Redis / MySQL / PostgreSQL / MongoDB / RabbitMQ / Kafka

- **Redis Stream ingress**: `RedisSpider` consumer groups (`XREADGROUP` / `XACK`), configurable via spider attrs or `settings.REDIS_STREAM_INFO`

- **Lightweight middleware & interceptor system** for easy extensions

- **High-performance C-extension hooks** for CPU-intensive tasks

- **Redis-compatible scheduler** (optional) for distributed crawling

- **Designed for high-concurrency, high-availability crawling**

---

## 📦 Installation

> **Note (≥ 0.3.0):** Core framework changes from 0.3.0 onward are developed with AIGC-assisted workflows. For the latest features and fixes before they land on PyPI, install from GitHub or source.

#### From PyPI

```bash
pip install scrapy_cffi

# Kafka request scheduler support
pip install "scrapy_cffi[kafka]"
```

#### From GitHub (latest main)

```bash
python -m pip install "scrapy_cffi @ git+https://github.com/aFunnyStrange/scrapy_cffi.git"
```

---

#### From source (unstable)
```bash
git clone https://github.com/aFunnyStrange/scrapy_cffi.git

cd scrapy_cffi

pip install -e .
```

---

## 🚀 Quick Start
```bash
scrapy-cffi startproject <project_name>

cd <project_name>

scrapy-cffi genspider <spider_name> <domain>

# Kafka start/work request queues
scrapy-cffi genspider --kafka <spider_name> <domain>

python runner.py
```

Generated `runner.py` imports the generated Spider class directly, and generated
`settings.py` assigns imported Scheduler, Extension, Pipeline, and Interceptor
classes instead of opaque strings. IDE navigation and completion therefore work
out of the box; legacy string import paths remain supported.

Streaming chat/SSE endpoints use the same request model:

```python
from scrapy_cffi.internet import HttpRequest, StreamResponse

yield HttpRequest(url=chat_url, stream=True, callback=self.parse_stream)

async def parse_stream(self, response: StreamResponse):
    async for event in response.aiter_sse():
        yield {"data": event.data}
```

For finite spiders, use `SCHEDULER_LOOP_END` to stop after a bounded number of
empty scheduler loops. Continuous Redis/RabbitMQ/Kafka spiders normally leave
it as `None`.

Framework maintainers can validate every generated Demo path serially with
`scrapy-cffi test all`. The command uses disposable local infrastructure,
removes each case's data before continuing, and retains crawler/server/broker
evidence under `artifacts/release-verification/<timestamp>/`. Use `--quick`
for generation, imports, topology plans, and unit tests without Docker.

---

## ⚙️ Settings & Deployment

`scrapy_cffi` now fully supports a flexible settings system:

- Load configuration from Python files or `.env` files

- Choose between **single-instance**, **cluster**, or **sentinel mode**

- Configure databases, message queues, and concurrency limits in one place

- Seamless integration with async Redis / MySQL / PostgreSQL / MongoDB managers

Generate local infra templates (optional):

```bash
scrapy-cffi infra generate
scrapy-cffi infra plan --topology cluster --services redis rabbitmq kafka
scrapy-cffi infra up --topology cluster --services redis rabbitmq kafka
scrapy-cffi infra down --topology cluster --services redis rabbitmq kafka
```

Generated infra is disposable, project-isolated local simulation only. In production, containerize only the crawler application; Redis/database/MQ services remain on real machines or native clusters and the crawler consumes their configured addresses directly.
Each generated `scrapy_cffi.toml` contains
`default.infra_project_name = "scrapy_cffi"`; change this prefix during
development and keep it unique across concurrently running projects. Compose
uses it to isolate container, network, and volume names. For `single`, omitting
`--services` starts all services still defined in the project-local
`infra/docker-compose.yml`. Edit that file's `image:` values or remove/comment
unwanted service blocks as needed. `infra up` preserves these edits; explicit
`infra generate` refreshes the generated templates.
The prefix is read only by Docker-management tooling. Crawler runtime code
continues to connect to Redis, databases, RabbitMQ, and Kafka through their
ordinary configured addresses and exposed ports.

Framework maintainers can run the complete release check through one entry:

```bash
scrapy-cffi test single
scrapy-cffi test sentinel
scrapy-cffi test cluster
scrapy-cffi test all
scrapy-cffi test all --quick  # no Docker: tests/import/topology plans
```

Every phase is summarized in `summary.md`/`summary.json`; crawler, server,
broker, cleanup, and console logs remain under
`artifacts/release-verification/<timestamp>/`.

Example `settings.py` snippet (Redis Sentinel):

```python
from scrapy_cffi.config import RedisInfo

settings.REDIS_INFO = RedisInfo(
    SENTINELS=[
        ("redis-sentinel-01.internal", 26379),
        ("redis-sentinel-02.internal", 26379),
        ("redis-sentinel-03.internal", 26379),
    ],
    MASTER_NAME="mymaster",
    USERNAME="crawler",
    PASSWORD="secret-from-env",
)
```

Optional Redis Stream consumer-group defaults (spider attrs override):

```python
from scrapy_cffi.models import RedisStreamConsumerInfo, RedisIngressMode

settings.REDIS_STREAM_INFO = RedisStreamConsumerInfo(
    MODE=RedisIngressMode.STREAM,
    STREAM_KEY="tasks:ingress",
    GROUP_NAME="scrapy-workers",
)
```

---

## 📖 Documentation

Full technical documentation and module-level guides are available in the [`docs/usage/`](https://github.com/aFunnyStrange/scrapy_cffi/tree/main/docs/usage) directory.

0.4.0 architecture and compatibility notes: [`docs/RELEASE-0.4.0.md`](https://github.com/aFunnyStrange/scrapy_cffi/blob/main/docs/RELEASE-0.4.0.md).

Release history: [`CHANGELOG.md`](https://github.com/aFunnyStrange/scrapy_cffi/blob/main/CHANGELOG.md) · Architecture: [`docs/ARCHITECTURE-ROADMAP.md`](https://github.com/aFunnyStrange/scrapy_cffi/blob/main/docs/ARCHITECTURE-ROADMAP.md) · **0.4.0**: [`docs/RELEASE-0.4.0.md`](https://github.com/aFunnyStrange/scrapy_cffi/blob/main/docs/RELEASE-0.4.0.md) · **0.3.3**: [`docs/RELEASE-0.3.3.md`](https://github.com/aFunnyStrange/scrapy_cffi/blob/main/docs/RELEASE-0.3.3.md).

---

## 📄 License

BSD 3-Clause License. See LICENSE for details.

---

## 🛠 Community Highlights

Inspired by the challenges of async Python crawling:

- Blocking requests and slow DB integration

- Complex deployment for distributed crawlers

- Need for fully concurrent HTTP & WebSocket requests

`scrapy_cffi` addresses these with a modular, high-performance framework that is **async-first**, **extensible**, and **deployment-ready**.
