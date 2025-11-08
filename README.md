## scrapy_cffi

> An asyncio-style web scraping framework inspired by Scrapy, powered by `curl_cffi`.

`scrapy_cffi` is a lightweight Python crawler framework that mimics the Scrapy architecture while replacing Twisted with `curl_cffi` as the underlying HTTP/WebSocket client. 

It is designed to be efficient, modular, and suitable for both simple tasks and large-scale distributed crawlers.

---

## ✨ Features

- **Scrapy-style architecture**: spiders, items, interceptors, pipelines, signals

- **Fully asyncio-based engine** for maximum concurrency

- **HTTP & WebSocket support**: built-in asynchronous clients

- **Flexible DB integration**: Redis, MySQL, MongoDB with async retry & reconnect

- **Message queue support**: RabbitMQ & Kafka

- **Configurable deployment**: settings system supporting .env files, single-instance, cluster mode, and sentinel mode

- **Lightweight middleware & interceptor system** for easy extensions

- **High-performance C-extension hooks** for CPU-intensive tasks

- **Redis-compatible scheduler** (optional) for distributed crawling

- **Designed for high-concurrency, high-availability crawling**

---

## 📦 Installation
#### From PyPI

```bash
pip install scrapy_cffi
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

---

## ⚙️ Settings & Deployment

`scrapy_cffi` now fully supports a flexible settings system:

- Load configuration from Python files or `.env` files

- Choose between **single-instance**, **cluster**, or **sentinel mode**

- Configure databases, message queues, and concurrency limits in one place

- Seamless integration with async Redis/MySQL/MongoDB managers

Example `settings.py` snippet:

```python
settings.REDIS_INFO.MODE = "sentinel"

settings.REDIS_INFO.SENTINELS = [("<master_host1>", "int(master_port1)"), ("<master_host2>", "int(master_port2)"), ("<master_host3>", "int(master_port3)")]

settings.REDIS_INFO.MASTER_NAME = "<master_name>"

settings.REDIS_INFO.SENTINEL_OVERRIDE_MASTER = ("master_host", "int(master_port)")
```

---

## 📖 Documentation
Full technical documentation and module-level guides are available in the [`docs/`](https://github.com/aFunnyStrange/scrapy_cffi/tree/main/docs/usage) directory.

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