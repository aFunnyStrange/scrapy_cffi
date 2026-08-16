# Multi-spider resource ownership

When **one event loop** runs **multiple spiders** (single `Crawler` + `run_all_spiders`, or `run_spiders` with multiple configs), use this table to avoid queue / dedup / stream key collisions.

## Mode A — one `Crawler`, shared base `SettingsInfo`

Each spider gets its own **scheduler instance**. Override per spider via class attributes or `settings_overlay`.

Scheduler families are preserved as well. A normal `Spider` keeps its
in-memory scheduler when Redis, RabbitMQ, or Kafka spiders share the Crawler.
There is no implicit promotion in `run_all_spiders`; only an explicit global
`settings.SCHEDULER` selects one scheduler class for all spiders.

| Resource | Scope | Isolation mechanism |
| -------- | ----- | ------------------- |
| Work queue (memory scheduler) | Per spider | `scheduler_queue_key` or `queue_name`; else `{QUEUE_NAME}:{name}` or `{name}_req` |
| Redis scheduler queue | Per spider | Same as above (`get_queue_key`) |
| Redis dedup (RedisDupeFilter) | Per spider | `redis_namespace` = spider name (auto when one spider per scheduler) |
| Redis list/stream **start** URL | Per spider | `redis_key` or `settings.REDIS_STREAM_INFO` + `resolve_redis_ingress` |
| Stream consumer group | Per spider / project | `redis_group`, `REDIS_STREAM_INFO.GROUP_NAME` |
| In-memory dedup | Per scheduler | Separate `MemoryDupeFilter` instance per scheduler |
| `SettingsInfo` fields | Per spider (optional) | `settings_overlay` on spider class |
| DB/MQ managers | **Shared** Crawler singleton | Same `REDIS_INFO` / pool for all spiders in one Crawler |
| `sessions` / `downloader` | Shared | Same loop, same global concurrency settings unless overlaid |

### Class attributes

```python
from scrapy_cffi.spiders import RedisSpider

class WorkerA(RedisSpider):
    name = "worker_a"
    scheduler_queue_key = "proj:worker_a:req"   # explicit queue
    redis_key = "proj:worker_a:start"
    settings_overlay = {"MAX_CONCURRENT_REQ": 20}

class WorkerB(RedisSpider):
    name = "worker_b"
    scheduler_queue_key = "proj:worker_b:req"
    redis_key = "proj:worker_b:start"
    settings_overlay = {"MAX_CONCURRENT_REQ": 5}
```

### Project-wide stream defaults

```python
from scrapy_cffi.models import RedisStreamConsumerInfo, RedisIngressMode

settings.REDIS_STREAM_INFO = RedisStreamConsumerInfo(
    MODE=RedisIngressMode.STREAM,
    GROUP_NAME="shared-group",
    # STREAM_KEY still overridden per spider via redis_key when set
)
```

Resolution order: **spider attribute → `REDIS_STREAM_INFO` → `{name}_redis_start`**.

---

## Mode B — `run_spiders` (multiple `Crawler`, one loop)

Each [`SpiderRunConfig`](../../scrapy_cffi/runner.py) carries its own `SettingsInfo` — separate Redis URLs, schedulers, managers.

```python
import scrapy_cffi

# sync
scrapy_cffi.run_spiders_sync([
    scrapy_cffi.SpiderRunConfig(settings=base_a, start_type=1),
    scrapy_cffi.SpiderRunConfig(settings=base_b, start_type=1),
])

# async (inside your loop)
# crawlers, tasks = await scrapy_cffi.run_spiders([...])
# await asyncio.gather(*tasks)
```

---

## Mode C — one loop per spider (thread / process)

```python
import threading
import scrapy_cffi

def run_in_thread(settings):
    scrapy_cffi.run_spider_sync(settings, new_loop=True)

threading.Thread(target=run_in_thread, args=(settings_a,)).start()
threading.Thread(target=run_in_thread, args=(settings_b,)).start()
```

Full process isolation: use `multiprocessing` + `run_spider_sync(..., new_loop=True)`.

---

## Example — two spiders, different queues, same loop

`runner.py` (project):

```python
import asyncio
from scrapy_cffi.scheduler import RedisScheduler
from scrapy_cffi.runner import run_all_spiders_sync
from myproject.settings import create_settings

# create_settings loads two spider classes from spiders/ directory
settings = create_settings(spider_path="spiders")
settings.SCHEDULER = RedisScheduler
settings.REDIS_INFO.URL = "redis://127.0.0.1:6379/0"

if __name__ == "__main__":
    run_all_spiders_sync(settings)
```

Spiders:

```python
# spiders/spider_alpha.py
from scrapy_cffi.spiders import Spider

class AlphaSpider(Spider):
    name = "alpha"
    scheduler_queue_key = "demo:alpha:req"
    start_urls = ["http://127.0.0.1:8002/"]

# spiders/spider_beta.py
class BetaSpider(Spider):
    name = "beta"
    scheduler_queue_key = "demo:beta:req"
    settings_overlay = {"DONT_FILTER": True}
    start_urls = ["http://127.0.0.1:8002/page2"]
```

Push work to distinct Redis lists (if using RedisScheduler):

```bash
redis-cli RPUSH demo:alpha:req "$(python -c 'import pickle,base64; ...')"
# Or use in-memory Scheduler — queues are in-process per scheduler_queue_key
```

---

## Related docs

- [2-spiders.md](./2-spiders.md) — RedisSpider / Stream
- [1-settings.md](./1-settings.md) — `REDIS_STREAM_INFO`, `QUEUE_NAME`
- [13-standalone-tools.md](./13-standalone-tools.md) — factories without Crawler
- [15-deduplication.md](./15-deduplication.md) — jump-hash, shutdown cleanup, per-spider namespaces
- [ARCHITECTURE-ROADMAP.md](../ARCHITECTURE-ROADMAP.md) — full decoupling plan
