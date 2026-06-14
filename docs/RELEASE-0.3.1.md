# scrapy_cffi 0.3.1 — Tool library decoupling

Focus: use `scrapy_cffi` as **standalone tools** (databases / mq / utils) without loading the full crawler stack.

## Highlights

- **Lazy imports**: root `scrapy_cffi`, `scrapy_cffi.utils`, `scrapy_cffi.tools` load symbols on demand.
- **Factory APIs**: `RedisManager.from_redis_info`, `*.from_db_info`, `from_rabbitmq_info`, …
- **Multi-spider**: `settings_overlay`, `run_spiders` / `run_spiders_sync`, resource ownership doc.
- **Media**: `filetype` + `pip install scrapy_cffi[media]` (no `python-magic` / `[windows]` / `[unix]`).

## Tool-only quick start

```python
from scrapy_cffi.utils.algorithm import do_sha1
from scrapy_cffi.databases import RedisManager
from scrapy_cffi.mq import RabbitMQManager

# or single namespace (lazy):
from scrapy_cffi.tools import RedisManager, canonical_request_url
```

## Docs

- [13-standalone-tools.md](usage/13-standalone-tools.md)
- [14-multi-spider-resources.md](usage/14-multi-spider-resources.md)
- [ARCHITECTURE-ROADMAP.md](ARCHITECTURE-ROADMAP.md)

## Install

```bash
pip install scrapy_cffi==0.3.1
pip install "scrapy_cffi[media]"   # optional MIME/image/video helpers
```

Stay on 0.2.7 for pre-AIGC baseline: [CHANGELOG.md](../CHANGELOG.md) section `[0.3.0]`.
