## scrapy_cffi

> An asyncio-style web scraping framework inspired by Scrapy, powered by `curl_cffi`.

`scrapy_cffi` is a lightweight Python crawler framework that mimics the Scrapy architecture while replacing Twisted with `curl_cffi` as the underlying HTTP/WebSocket client. 

It is designed to be efficient, modular, and suitable for both simple tasks and large-scale distributed crawlers.

---

## ✨ Features

- **Scrapy-style architecture**: spiders, items, interceptors, pipelines, signals

- **Fully asyncio-based engine** for maximum concurrency

- **HTTP & WebSocket support**: built-in asynchronous clients

- **Flexible DB integration**: Redis, MySQL, **PostgreSQL**, MongoDB with async retry & reconnect

- **Message queue support**: RabbitMQ & Kafka (single / cluster)

- **Configurable deployment**: settings system supporting `.env`, single-instance, **sentinel**, and **cluster** mode

- **`scrapy-cffi geninfra`**: generate local Docker Compose templates for Redis / RabbitMQ / Kafka topologies

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

python runner.py
```

**Notes:**
> The CLI command is `scrapy_cffi` in versions ≤0.1.4 and `scrapy-cffi` in versions >0.1.4 for **improved usability**.

> Starting from `scrapy-cffi >= 0.2.5`, `RedisScheduler` and `RabbitMqScheduler` no longer automatically terminate when the queue is empty. For finite/terminable spiders, use `SCHEDULER_LOOP_END` to specify the number of scheduler loops before automatic exit. For continuous-listening spiders (`RedisSpider`, `RabbitMqSpider`, or custom persistent spiders), leave `SCHEDULER_LOOP_END` as `None`. This change only affects automatic termination; task scheduling remains fully functional.

---

## ⚙️ Settings & Deployment

`scrapy_cffi` now fully supports a flexible settings system:

- Load configuration from Python files or `.env` files

- Choose between **single-instance**, **cluster**, or **sentinel mode**

- Configure databases, message queues, and concurrency limits in one place

- Seamless integration with async Redis / MySQL / PostgreSQL / MongoDB managers

Generate local infra templates (optional):

```bash
scrapy-cffi geninfra
scrapy-cffi geninfra --redis cluster --rabbitmq cluster --kafka cluster
```

Example `settings.py` snippet (Redis Sentinel):

```python
settings.REDIS_INFO.MODE = "sentinel"

settings.REDIS_INFO.SENTINELS = [("<sentinel_host1>", "int(sentinel_port1)"), ("<sentinel_host2>", "int(sentinel_port2)"), ("<sentinel_host3>", "int(sentinel_port3)")]

settings.REDIS_INFO.MASTER_NAME = "<master_name>"

settings.REDIS_INFO.SENTINEL_OVERRIDE_MASTER = ("master_host", "int(master_port)")
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

Release history: [`CHANGELOG.md`](https://github.com/aFunnyStrange/scrapy_cffi/blob/main/CHANGELOG.md).

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