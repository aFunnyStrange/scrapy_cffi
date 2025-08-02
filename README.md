## scrapy_cffi

> An asyncio-style web scraping framework inspired by Scrapy, powered by `curl_cffi`.

`scrapy_cffi` is a lightweight asynchronous crawling framework that mimics the Scrapy architecture while replacing Twisted with `curl_cffi` as the underlying HTTP/WebSocket client. It is designed to be efficient, extensible, and suitable for both simple tasks and complex distributed crawlers.

---

## ✨ Features

- Familiar Scrapy-style components: spiders, items, interceptors, pipelines
- Fully asyncio-based engine
- Built-in support for HTTP and WebSocket requests
- Lightweight signal system
- Plug-in ready interceptor and task manager design
- Redis-compatible scheduler (optional)
- Designed for high-concurrency crawling

---

## 📦 Installation
#### From PyPI

```bash
pip install scrapy_cffi
```

#### From source
```bash
git clone https://github.com/aFunnyStrange/scrapy_cffi.git
cd curl_cffi
pip install -e .
```

## 🚀 Quick Start
```bash
scrapy_cffi startproject <project_name>
cd <project_name>
scrapy_cffi genspider <spider_name> <domain>
python runner.py
```

## 📖 Documentation
Technical module-level documentation can be found in the [`docs/`](https://github.com/aFunnyStrange/scrapy_cffi/tree/main/docs/usage) directory on GitHub.
Each core component (engine, downloader, middleware, etc.) has its own `.md` file.

## 📄 License
This project is licensed under the BSD 3-Clause License. Portions of the code (specifically item.py) are adapted from the Scrapy project.
See LICENSE for details.
