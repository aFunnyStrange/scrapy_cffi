# scrapy_cffi 0.3.2 — Dedup cleanup, C extensions, demo stability

Follow-up to [0.3.1](RELEASE-0.3.1.md) (tool-library decoupling). This release fixes shutdown dedup cleanup, documents cluster routing, and hardens the demo / templates.

## Highlights

- **Shutdown dedup cleanup**: when `SCHEDULER_PERSIST = False`, Ctrl+C or normal exit deletes ingress queue, work queue, and dedup keys (`cffiFilter_*`) via `DedupKeyRouter.cleanup_keys()`.
- **Per-spider dedup**: each spider gets its own Redis namespace (`cffiFilter_new_seen:<spider.name>`); ingress / start URLs skip dedup.
- **`scrapy-cffi cinstall`**: install locally built Bloom (or other) ctypes binaries once into the user system store; `startproject` scaffolds `cpy_resources/`.
- **`allowed_domains`**: hostname-only matching (Scrapy-style); `127.0.0.1` matches any port.

## Dedup & shutdown quick reference

| Setting | Effect |
| ------- | ------ |
| `SCHEDULER_PERSIST = False` (default) | On shutdown, delete Redis ingress / queue / dedup keys |
| `SCHEDULER_PERSIST = True` | Keep keys across runs (demo Rabbit mode) |
| `DEDUP_TTL > 0` | Auto-expire dedup keys (recommended hint in cluster mode) |
| `redis_namespace` | Per-spider dedup key suffix (set automatically on schedulers) |

Re-run after a clean shutdown with `SCHEDULER_PERSIST = False` should not hit stale fingerprints. If keys remain from an older version, delete manually:

```bash
redis-cli DEL cffiFilter_new_seen:customRedisSpider cffiFilter_sent_seen:customRedisSpider
```

## C extensions (Bloom)

PyPI wheels ship Python wrappers and pure-Python fallbacks only — **not** OS-specific `.dll` / `.so` files.

```bash
scrapy-cffi startproject myproj          # includes cpy_resources/bloom/ skeleton
scrapy-cffi cinstall --init bloom          # add skeleton to an existing project
# build libbloom.* → cpy_resources/bloom/build/
scrapy-cffi cinstall bloom --require-binary
scrapy-cffi cinstall --list
```

Details: [12-cpython.md](usage/12-cpython.md) · build notes: `scrapy_cffi/cpy/cpy_resources/bloom/BUILD.md`.

## Docs

- [15-deduplication.md](usage/15-deduplication.md) — architecture, jump-hash, when not to add a dedup service
- [0-start.md](usage/0-start.md) §6 — `cinstall`
- [2-spiders.md](usage/2-spiders.md) — `allowed_domains` (hostname only)

## Install

```bash
pip install scrapy_cffi==0.3.2
pip install "scrapy_cffi[media]"   # optional MIME/image/video helpers
```

Previous: [0.3.1 tools](RELEASE-0.3.1.md) · Full history: [CHANGELOG.md](../../CHANGELOG.md).
