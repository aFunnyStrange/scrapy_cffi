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

- **Request-scoped self-built TLS profiles**: select an ABI-compatible custom
  curl wrapper once, then explicitly choose its registered alias through
  `impersonate` on each HTTP, media, streaming, or WebSocket request

- **Layered resource architecture**: parallel Redis, RabbitMQ, Kafka,
  SQLAlchemy, and MongoDB infra clients; stable repositories; and one typed
  service that owns lifecycle and bounded client replacement

- **Message queue scheduling**: Redis, RabbitMQ, and Kafka capabilities behind
  repository Protocols (separate Kafka start/work topics with manual acknowledgement)

- **Configurable deployment**: settings system supporting `.env`, single-instance, **sentinel**, and **cluster** mode

- **`scrapy-cffi infra`**: generate and manage independent project-local Docker infrastructure for Redis / MySQL / PostgreSQL / MongoDB / RabbitMQ / Kafka

- **Redis Stream ingress**: `RedisSpider` consumer groups (`XREADGROUP` / `XACK`), configurable via spider attrs or `settings.REDIS_STREAM_INFO`

- **Lightweight middleware & interceptor system** for easy extensions

- **Stable CPU platform adapters** with optional Rust acceleration and safe
  Python fallbacks, including Protobuf and Bloom filtering

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

# Optional Rust-accelerated Protobuf codec with automatic Python fallback
pip install "scrapy_cffi[protobuf]"

# Optional Rust-accelerated Bloom filter with identical Python fallback semantics
pip install "scrapy_cffi[bloom]"
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

# Standalone TLS inspection demo
scrapy-cffi demo -tls

python runner.py
```

Generated `runner.py` imports the generated Spider class directly, and generated
`settings.py` assigns imported Scheduler, Extension, Pipeline, and Interceptor
classes instead of opaque strings. IDE navigation and completion therefore work
out of the box; legacy string import paths remain supported.

Every generated project contains a `profiles/` reference directory. Place each
self-built, ABI-specific runtime under `profiles/artifacts/<runtime>/`, copy the
example manifest there as `scrapy_cffi_profiles.toml`, and point
`CURL_CFFI_RUNTIME_DIR` at that exact runtime directory. The historical
`SCRAPY_CFFI_CURL_CFFI_NATIVE_DIR` name remains accepted for compatibility.

Streaming chat/SSE endpoints use the same request model:

```python
from scrapy_cffi.internet import HttpRequest, StreamResponse

yield HttpRequest(url=chat_url, stream=True, callback=self.parse_stream)

async def parse_stream(self, response: StreamResponse):
    async for event in response.aiter_sse():
        yield {"data": event.data}
```

Self-built `curl-impersonate` profiles are configured in two separate steps.
The setting chooses the compatible native wrapper; each request chooses its
profile explicitly, so unrelated requests never inherit a global fingerprint:

```python
from pathlib import Path

from scrapy_cffi.internet import HttpRequest
from scrapy_cffi.settings import SettingsInfo


settings = SettingsInfo(
    CURL_CFFI_RUNTIME_DIR=Path("D:/native/my-curl-build"),
)

yield HttpRequest(
    url="https://tls.peet.ws/api/all",
    impersonate="my-browser-stable",
    callback=self.parse,
)
```

The framework ships no concrete custom profile. Users declare aliases in the
artifact directory's optional `scrapy_cffi_profiles.toml`, or register them
programmatically with `scrapy_cffi.profiles.register_profile`.

WebSocket connections are long-lived and event-driven. The initial
`send_message` remains part of the connecting `WebSocketRequest` and is sent
before receiving; callbacks stop listening explicitly with
`response.stop_listening()`.

See [the 0.4.3 release guide](docs/en/RELEASE-0.4.3.md) for the runtime/profile
boundary, concurrency defaults, session rate limiting, timeout delivery, and
resource ownership rules.

Finite completion is event-driven. A naturally returning `Spider.start()` is a
finite producer; standard Redis/RabbitMQ/Kafka Spiders may set a positive
`start_request_limit` to return after that many accepted ingress messages.
Their default `None` means continuous listening, and an empty broker read never
signals completion. Engine shutdown is scoped per spider and waits for that
spider's callbacks, downloader work, and WebSocket listeners. A queued
`WebSocketRequest` carrying a
`websocket_id` is always an existing-connection send and is never converted
into a new connection if the original listener has already closed.

See [the mandatory verification contract](docs/TESTING.md) before changing the
framework or generated templates.

Framework maintainers can validate every generated Demo path serially with
`scrapy-cffi test all`. The command uses disposable local infrastructure,
removes each case's data before continuing, and retains crawler/server/broker
evidence under `artifacts/release-verification/<timestamp>/`. Use `--quick`
for generation, imports, topology plans, and unit tests without Docker.

---

## ⚙️ Settings & Deployment

`scrapy_cffi` now fully supports a flexible settings system:

- Develop with typed Python settings and deploy with one readable `.env` file;
  nested models use `__` keys and complex values support multiline JSON

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

Full technical documentation and module-level guides are available in [English](docs/en/README.md) and [简体中文](docs/cn/README.md).

0.4.0 architecture and compatibility notes: [`docs/en/RELEASE-0.4.0.md`](docs/en/RELEASE-0.4.0.md).

Release history: [`CHANGELOG.md`](CHANGELOG.md) · Architecture: [`docs/en/ARCHITECTURE-ROADMAP.md`](docs/en/ARCHITECTURE-ROADMAP.md) · **0.4.0**: [`docs/en/RELEASE-0.4.0.md`](docs/en/RELEASE-0.4.0.md) · **0.3.3**: [`docs/en/RELEASE-0.3.3.md`](docs/en/RELEASE-0.3.3.md).

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
