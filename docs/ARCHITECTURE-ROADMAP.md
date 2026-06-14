# Architecture Roadmap — Tool Library + Crawler Framework

This document records the decoupling analysis and phased execution plan for `scrapy_cffi`.

## Goals

1. **Independent tool library** — `utils`, `databases`, `mq` usable without importing `crawler` / full `core`.
2. **Crawler framework unchanged in spirit** — one asyncio loop may host multiple spiders; each spider owns scheduler keys and optional settings overlays.
3. **Multi-loop mode** — upper layers may run one `Crawler` per thread/process with `new_loop=True`.

## Layer model

| Layer | Packages | Depends on |
| ----- | -------- | ---------- |
| **Tier-0 tools** | `databases/*`, `mq/*`, `utils/algorithm`, `utils/jsonLoad`, `models/*` | Third-party only |
| **Tier-1 runtime** | `dupefilter/fingerprint`, `settings`, `redis_ingress` | Tier-0 + minimal types |
| **Framework** | `crawler`, `core`, `spiders`, `runner` | Tier-0/1 |

## Current state (baseline)

### Already good

- One file per DB backend (`redis.py`, `mysql.py`, …).
- `TYPE_CHECKING` for `Crawler` in tool modules.
- Per-spider scheduler instances; `queue_key_for_name`, `redis_namespace`.
- `redis_ingress`, `sqlalchemy_base` extractions.

### Gaps (addressed in phases below)

| Gap | Phase |
| --- | ----- |
| Root `import scrapy_cffi` loads full crawler | 1 — `runner.py`, lazy root |
| `databases` / `mq` incomplete `__all__` | 1 |
| Only `from_crawler` documented | 1 — `from_*_info` |
| Single shared `SettingsInfo` per `Crawler` | 2 — `settings_overlay`, `run_spiders` |
| Scheduler imports `extensions.signals` at import time | 3 — `_signals` helper |
| Dupefilter tied to `core.Request` | 3 — `fingerprint.py` |

## Phase 1 — Public surface ✅

- [x] `mq/__init__.py`, expanded `databases/__init__.py`
- [x] `runner.py`; root `__init__.py` lazy exports
- [x] `from_redis_info`, `from_db_info`, `from_rabbitmq_info`, `from_kafka_info`, `from_mongodb_info`
- [x] `docs/usage/13-standalone-tools.md`

## Phase 2 — Multi-spider settings ✅

- [x] `Spider.settings_overlay` + `merge_spider_settings()`
- [x] `run_spiders()` — multiple `Crawler` instances, one loop
- [x] `docs/usage/14-multi-spider-resources.md` — ownership table + example

## Phase 3 — Boundary cleanup (ongoing)

- [x] `dupefilter/fingerprint.py`
- [x] `core/scheduler/_signals.py` — lazy signal emit
- [x] `utils/__init__.py` lazy barrel; submodule import paths documented in `9-util.md` / `13-standalone-tools.md`
- [x] `run_spiders_sync`
- [x] `dupefilter/routing.py` — `DedupKeyRouter` (cluster jump-hash key affinity, decoupled from scheduler)

### Mode A — Single loop, multiple spiders (one `Crawler`)

```text
run_all_spiders(settings)
  └─ Crawler
       ├─ Engine(spider_a) + Scheduler_a  ← settings + settings_overlay
       └─ Engine(spider_b) + Scheduler_b
```

Queue / dedup / stream keys isolated via `scheduler_queue_key`, `redis_namespace`, `REDIS_STREAM_INFO`.

### Mode B — Single loop, multiple crawlers

```text
run_spiders([SpiderRunConfig(...), SpiderRunConfig(...)])
  └─ gather(start_engines) per Crawler
```

Each config carries its own `SettingsInfo` (separate Redis URL, concurrency, etc.).

### Mode C — One loop per spider (thread/process)

```text
run_spider_sync(settings_a, new_loop=True)  # thread 1
run_spider_sync(settings_b, new_loop=True)  # thread 2
```

## Standalone import cheat sheet

See [docs/usage/13-standalone-tools.md](usage/13-standalone-tools.md).

## References

- Release notes: [RELEASE-0.3.2.md](RELEASE-0.3.2.md) · [RELEASE-0.3.1.md](RELEASE-0.3.1.md)
- Dedup architecture: [usage/15-deduplication.md](usage/15-deduplication.md)
- Changelog: [CHANGELOG.md](../CHANGELOG.md)
