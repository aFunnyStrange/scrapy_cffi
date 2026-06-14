# Deduplication architecture

How Bloom filters, Redis SET dedup, and cluster jump-hash routing fit together — and when **not** to add another service layer.

## What each piece does

| Component | Role |
| --------- | ---- |
| **Fingerprint** (`dupefilter/fingerprint.py`) | Canonical URL + headers → SHA1; no Redis |
| **MemoryDupeFilter / BloomDupeFilter** | In-process dedup for local `Scheduler` |
| **RedisDupeFilter** | SET + Lua script (`do_filter`) in Redis |
| **RedisBloomDupeFilter** | Redis bitmap Bloom (`do_bloom_filter`) — lower memory, small FP rate |
| **DedupKeyRouter** (`dupefilter/routing.py`) | Maps fingerprint → `{new_seen, sent_seen}` keys |

## Cluster jump-hash — purpose

Redis Cluster routes keys by **hash slot**. Dedup keys must land on the correct node.

`DedupKeyRouter` uses **jump consistent hash** over cluster startup nodes (`utils.algorithm.get_node`) to append `:{host:port}` to key names. That is:

- **Key affinity** (same URL → same shard keys)
- **Not** crawler load balancing
- **Not** a replacement for Redis Cluster’s own routing

The crawler still talks to one `RedisManager` cluster client; only **key names** are sharded.

## Separate dedup service?

| Approach | Pros | Cons |
| -------- | ---- | ---- |
| **Current (in-process router + Redis)** | Simple deploy; works offline in tests; no extra hop | Jump-hash logic lives in framework (now isolated in `routing.py`) |
| **Dedicated dedup Redis (single/sentinel)** | No jump-hash; one SET namespace; easy ops | Second Redis to run; still one logical store |
| **HTTP/gRPC dedup microservice** | Central policy, language-agnostic | New SPOF unless HA; latency; you re-implement Bloom/cluster rules |
| **RedisBloom / Redis Stack module** | Server-side structures | Different ops model; not always available in cluster |

**Practical recommendation**

1. **Most teams**: single Redis or sentinel for **both** queue + dedup → use `RedisDupeFilter`, no jump-hash.
2. **Large scale, shared cluster**: keep jump-hash router; configure via settings only (`FILTER_KEY`, `DEDUP_TTL`, `BLOOM_INFO`, spider `redis_namespace`).
3. **Avoid** a custom dedup service unless you need cross-language clients or centralized dedup policy — Redis **is** already the distributed dedup service.

## Configuration (no spider code for cluster routing)

```python
settings.REDIS_INFO.MODE = "cluster"
settings.REDIS_INFO.CLUSTER_NODES = [{"host": "127.0.0.1", "port": 7000}, ...]
settings.FILTER_KEY = "myproject"          # → myproject_new_seen / myproject_sent_seen
settings.DEDUP_TTL = 86400                 # optional key expiry (cluster cleanup hint)
settings.DUPEFILTER = "scrapy_cffi.dupefilter.api.RedisDupeFilter"
# or RedisBloomDupeFilter for bitmap bloom in Redis

# Per-spider namespace (multi-spider one Crawler):
class MySpider(Spider):
    name = "worker_a"
    # scheduler sets redis_namespace=spider.name on RedisScheduler dedup
```

Bloom tuning: `settings.BLOOM_INFO` (`SIZE`, `EXPECTED`, `HASH_COUNT`).

## Shutdown cleanup (`SCHEDULER_PERSIST`)

When `SCHEDULER_PERSIST` is **False** (default), `Crawler.shutdown()` deletes:

- Spider ingress key (`redis_key`) and distributed work queue
- Dedup keys from `RedisDupeFilter.dedup_cleanup_keys()` → `DedupKeyRouter.cleanup_keys()`

This runs on normal exit and on **Ctrl+C** (`KeyboardInterrupt` in `runner.py`).

| Mode | Keys removed |
| ---- | ------------ |
| Single / sentinel | `{FILTER_KEY}_new_seen[:namespace]`, `{FILTER_KEY}_sent_seen[:namespace]` |
| Cluster | Same bases with `:{host:port}` suffix per startup node |

**Notes**

- **Cluster**: jump-hash spreads fingerprints across shard suffixes; cleanup deletes all known node suffix keys. Residual keys are possible — use `DEDUP_TTL` as a safety net.
- **Rabbit demo** sets `SCHEDULER_PERSIST = True` so dedup keys survive across runs (intentional).
- **Re-run still deduping?** Keys from a pre-0.3.2 run may remain; delete manually or set `SCHEDULER_PERSIST = False` and exit cleanly once.

Ingress / `start_urls` requests carry `meta["is_start_url"]` and bypass dedup in `RedisScheduler` / `RabbitMqScheduler.put`.

## Standalone tool use

```python
from scrapy_cffi.dupefilter.routing import DedupKeyRouter
from scrapy_cffi.databases import RedisManager

router = DedupKeyRouter.from_redis_manager(settings, redis_manager, namespace="spider_a")
keys = router.for_fingerprint("abc123fingerprint...")
# keys.new_seen, keys.sent_seen
```

## Related

- Multi-spider key ownership: [14-multi-spider-resources.md](./14-multi-spider-resources.md)
- Standalone imports: [13-standalone-tools.md](./13-standalone-tools.md)
- Architecture roadmap: [ARCHITECTURE-ROADMAP.md](../ARCHITECTURE-ROADMAP.md)
