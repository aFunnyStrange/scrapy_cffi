# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Architecture roadmap: [docs/ARCHITECTURE-ROADMAP.md](docs/ARCHITECTURE-ROADMAP.md) · **0.3.2** release: [docs/RELEASE-0.3.2.md](docs/RELEASE-0.3.2.md) · **0.3.1** tools: [docs/RELEASE-0.3.1.md](docs/RELEASE-0.3.1.md)

## [Unreleased]
### Added
- Shared single-flight reconnect controller for database/MQ adapters. Concurrent
  failures now collapse into one transport rebuild and respect crawler shutdown.
- `scripts/verify_demo.py`, a one-command serial verifier for Memory, Redis,
  RabbitMQ, and Kafka demos. It starts the generated HTTP/WebSocket servers,
  performs real start and incremental requests, retains per-mode framework,
  console, server, broker, and PASS/FAIL logs, and removes disposable
  containers/volumes before continuing.
- `KafkaSpider` / `KafkaScheduler` with separate start and work topics, compressed request payloads, Redis-backed dedup/session state, and manual contiguous offset commits.
- Persistent Session Cookie Hash state and adaptive request-state compression.
- Independent `geninfra` development stack for Redis, MySQL, PostgreSQL, MongoDB, RabbitMQ, and Kafka, with PowerShell/shell `init`, `reset`, and `destroy` scripts.
- `geninfra --all` local simulations for Redis Sentinel/Cluster, RabbitMQ Cluster, and Kafka Cluster. Compose project names derive from crawler project + topology, isolating containers, networks, and volumes across projects.
- `production-endpoints.example.toml` and production connection settings for real infrastructure hosts: Redis ACL/Sentinel auth/TLS/timeouts/address remap, RabbitMQ timeout/heartbeat, and Kafka SASL/TLS/client timeout.

### Changed
- Redis keeps its native `redis.asyncio.Redis` API and handles retry only at
  `execute_command`; RabbitMQ, Kafka, and SQLAlchemy managers now use explicit
  reconnectable methods instead of global `__getattribute__` interception.
  Mongo collections retain the native Motor type for IDE completion through a
  typed internal proxy.
- `RabbitMqScheduler` and `KafkaScheduler` still require Redis for distributed
  deduplication. With `SCHEDULER_PERSIST=False`, normal exit and Ctrl+C now also
  delete their start/work queues or topics along with Redis dedup/session state.
  Demo broker modes exercise this cleanup by default.
- RabbitMQ exchange durability is now stable across persistent and transient
  schedulers, allowing both modes to share an exchange without AMQP
  `PRECONDITION_FAILED`; queue/message durability still follows
  `SCHEDULER_PERSIST`.
- Local RabbitMQ healthchecks now wait for AMQP port connectivity instead of
  reporting healthy while the broker is still starting its listeners.
- Crawler shutdown preparation is now locked and idempotent. Concurrent normal
  completion, Ctrl+C, and explicit `crawler.shutdown()` can no longer race by
  setting the global stop event before unfinished Redis/RabbitMQ requests are
  requeued.
- Project Docker Compose now contains only the crawler application and no longer owns or waits for database/MQ containers.
- Docker infrastructure templates are explicitly development-only. Production containerizes the crawler application and connects directly to databases/MQ on real machines or native clusters.
- Redis and MQ node lists infer Sentinel/cluster mode; Kafka replication defaults to the configured bootstrap-node count for constructed cluster settings.
- Local Kafka Compose and broker-test stacks use the official Apache Kafka KRaft image; obsolete Bitnami/ZooKeeper instructions were removed.
- Generated `runner.py` and `settings.py` now use explicit class imports for spiders, schedulers, extensions, pipelines, and interceptors. String import paths remain backwards compatible.
- `.env` export serializes configured classes back to stable import paths instead of dropping components or writing unusable `<class ...>` representations.

### Removed
- The obsolete demo README and monolithic project Compose database/MQ definitions. Generated demos now use the topology-aware local-infra guide.

### Fixed
- Ctrl+C now cancels active work before broker shutdown, requeues unfinished Redis/RabbitMQ requests, leaves Kafka offsets uncommitted, and snapshots Session cookies before Redis writes are disabled.
- `KafkaInfo(HOST=..., PORT=...)` now produces a native `host:port` bootstrap endpoint instead of inheriting the AMQP URL scheme.
- Package metadata now declares the actual Python 3.9 minimum, uses the `python-dotenv` distribution name, and avoids Python 3.10-only union annotations.
- Response/exception interceptor chains now continue correctly on `None` and preserve exceptions after every interceptor declines to handle them.
- Redis start-request polling no longer leaks one pending stop task per message; synchronous runners now execute crawler shutdown even when an engine raises, and repeated Kafka shutdown clears closed client state.
- Redis Sentinel now uses the asyncio client, Redis Cluster reconnects replace
  the command target without stale bound-method caches, and RabbitMQ reconnects
  discard Queue objects owned by the previous channel.
- MongoDB is initialized before first use; crawler shutdown now closes MongoDB and Redis clients, while Redis no longer swallows `KeyboardInterrupt` during retries.
- Response objects no longer share a mutable default `meta` dictionary across requests.
- Scheduler state decoding uses bounded streaming decompression and rejects logical payloads above 16 MiB, preventing oversized broker messages or compression bombs from exhausting crawler memory.
- `demo -r` works with current redis-py: plain `redis://` connections no longer receive an invalid `ssl=False` keyword, and RESP2 is selected by default for compatibility across Redis server versions.
- `genspider` and every demo variant bind `runner.DEFAULT_SPIDER` to an existing generated class instead of the removed hard-coded `spiders.CustomSpider` string.

---
## [0.3.2] - 2026-05-29
### Added
- `scrapy-cffi cinstall` — install user-built ctypes modules into a per-user system store (`SCRAPY_CFFI_CPY_DIR`); `--init`, `--list`, `--path`, `--remove`.
- `startproject` scaffolds `cpy_resources/bloom/` (`wrapper.py`, `fallback.py`, empty `build/`); wheels ship no prebuilt native libs — see `cpy/cpy_resources/bloom/BUILD.md`.
- `DedupKeyRouter.cleanup_keys()` and `RedisDupeFilter.dedup_cleanup_keys()` — shutdown cleanup for single-node and cluster dedup keys.
- `utils/domain.py` — Scrapy-style hostname-only `allowed_domains` matching (ports ignored).
- [docs/usage/15-deduplication.md](docs/usage/15-deduplication.md) — Bloom / Redis dedup, jump-hash routing, when not to add a dedup service.
- Unit tests: domain filter, dedup routing, per-spider Redis dedup isolation, scheduler smoke (memory / Redis / Rabbit / Kafka init).

### Changed
- Per-spider dedup isolation: schedulers pass `redis_namespace=spider.name` into `RedisDupeFilter`.
- `RedisScheduler` / `RabbitMqScheduler.put` skip dedup for `dont_filter` or `meta["is_start_url"]` (ingress / start URLs).
- Demo and project templates: `allowed_domains` use hostnames only; Redis demo sets `SCHEDULER_PERSIST = False` (Rabbit demo keeps `True`).
- Lazy submodule imports for `scrapy_cffi.crawler`, `databases`, and `mq` so optional deps do not break unrelated modes.

### Fixed
- Dedup Redis keys were not deleted on shutdown (Ctrl+C or normal exit) after the `DedupKeyRouter` refactor — cleanup referenced removed `new_seen` / `sent_seen` attributes on `RedisDupeFilter`.
- `RedisDupeFilter.mark_sent` cluster shard key selection.
- Circular imports on crawler startup (extensions, downloader, runner type hints).
- `KafkaManager.__init__` no longer requires a running asyncio event loop.
- Python 3.9-compatible type hints in Redis dupefilter and ingress modules.
- Demo runner stability (domain filter, stale spider files, pipeline imports).

---
## [0.3.1] - 2026-05-29
### Added
- Architecture roadmap [docs/ARCHITECTURE-ROADMAP.md](docs/ARCHITECTURE-ROADMAP.md); [docs/usage/13-standalone-tools.md](docs/usage/13-standalone-tools.md); [docs/usage/14-multi-spider-resources.md](docs/usage/14-multi-spider-resources.md).
- `scrapy_cffi.runner` — `run_spider*`, `run_spiders`, `run_spiders_sync`, `SpiderRunConfig`; root package lazy-imports runner APIs.
- `scrapy_cffi.tools` lazy namespace for databases / mq / fingerprint / settings.
- Manager factories: `from_redis_info`, `from_db_info`, `from_mongodb_info`, `from_rabbitmq_info`, `from_kafka_info`.
- `merge_spider_settings`, spider `settings_overlay` for per-spider settings on one Crawler.
- `dupefilter/fingerprint.py`; scheduler signal helpers in `core/scheduler/_signals.py`.
- `mq/__init__.py`; expanded `databases/__init__.py` exports.
- Optional extra `scrapy_cffi[media]` (`filetype`, `Pillow`, `hachoir`).

### Changed
- `utils` package: lazy barrel via `__getattr__`; recommended imports are submodules (`utils.algorithm`, `utils.media`, …).
- Framework internals import utils submodules directly (avoid eager barrel load on crawler startup).
- Media MIME sniffing uses `filetype` (cross-platform).

### Removed
- Optional extras `scrapy_cffi[windows]` and `scrapy_cffi[unix]` (`python-magic`). Use `scrapy_cffi[media]` instead.

---
## [0.3.0] - 2026-05-29
### Added
- `scrapy-cffi geninfra` — generate Redis / RabbitMQ / Kafka topology Docker Compose templates under `infra/`.
- Broker integration tests consolidated under `tests/test_broker` (single, sentinel, cluster CRUD smoke tests).
- Redis Stream consumer-group ingress for `RedisSpider` (`redis_start_mode`, `redis_group`, `XACK` after scheduling).
- `settings.REDIS_STREAM_INFO` and `RedisStreamConsumerInfo` — project-wide stream/list ingress defaults decoupled from spider class attributes.
- `redis_ingress.resolve_redis_ingress()` — merge spider attrs, settings defaults, and framework fallbacks.
- `SQLAlchemyPostgresManager` with async SQLAlchemy helpers (`execute`, `fetchone`, `fetchall`, `run_stmt`).
- Shared `BaseSQLAlchemyManager` for MySQL/PostgreSQL; pool options on `SqlAlchemyEngineInfo` (`ECHO`, `POOL_PRE_PING`, `POOL_SIZE`, `MAX_OVERFLOW`).
- README: direct install from GitHub (`pip install "scrapy_cffi @ git+https://github.com/aFunnyStrange/scrapy_cffi.git"`).

### Changed
- **From 0.3.0**, core framework evolution is AIGC-assisted; prefer GitHub/source install for latest changes before PyPI catches up.
- Redis / RabbitMQ / Kafka broker adapters refactored for sentinel, cluster, and multi-node failover.
- `RedisManager` cluster mode (`RedisCluster`, `address_remap`, async cluster client).
- `RedisScheduler` / `RedisSpider` delegate start-request dequeue and ack to `redis_ingress`.
- Crawler eagerly `init()` / `close()` MySQL and PostgreSQL managers when `resolved_url` is configured.
- Demo templates, `docker-compose.yml`, and `docs/usage/11-mq.md` updated for broker topologies.
- Request deduplication fingerprint canonicalizes URL query parameters (sorted key/value pairs).

### Fixed
- `RedisScheduler` no longer checks `RABBITMQ_INFO` by mistake.
- Kafka cluster compose: healthcheck port and `depends_on` deadlock on multi-broker stacks.
- RabbitMQ cluster connect iterates all configured nodes.
- Robots.txt allow-domain checks use `urlparse().hostname` instead of `netloc` (port-safe matching).
- Redis cluster `dequeue_request` decode when payload is already `str`.

### Removed
- Legacy standalone broker test dirs `tests/test_redis`, `tests/test_rabbitmq`, `tests/test_kafka` (assets migrated to `tests/test_broker`).

---
## [0.2.7] - 2026-05-15
### Added
- Added `extract_json_chain` for chained JSON extraction from nested or encoded JSON text.

### Changed
- Improved asyncio task and scheduler lifecycle compatibility across Python versions.

---
## [0.2.6] - 2025-11-22
### Added
- settings `SCHEDULER_LOOP_END`, Allow `Spider` to use `RedisScheduler`, `RabbitMqScheduler`.

## Fixed
- Fixed scheduler empty signal loss.
- After testing, `aio_pika` does not fully support a large number of concurrent robust connections.

---
## [0.2.5] - 2025-11-22
### Added
- settings `MAX_SCHEDULER_LOOP_NUM`

### Changed
- Deferred coroutine creation to avoid un-awaited coroutine warnings during `Ctrl+C`.
- Replaced the old recursive task-spawning scheduler with a centralized multi-worker `scheduler_loop` model, eliminating deep task-chain growth and event-loop starvation, and delivering multi-fold throughput and stability improvements under high concurrency.

---
## [0.2.3~0.2.4] - 2025-11-2~2025.11.8
### Changed
- Cross-platform and cross-version testing
- Refactored the third-party library **blackboxprotobuf**, inheriting only the required APIs instead of depending on the full external package.

---
## [0.2.2] - 2025-11-1
### Added
- Updated test cases related to the MQ cluster
- Uploaded C implementation of Bloom filter
- WebSocket message sending now requires specifying flags -> curlflags
- Added `ping_data` maintenance for WebSocket; this ping is user-defined, while protocol-level ping requests are automatically handled by the library and do not require user intervention
- Replaced asyncio coroutines using `inspect` for detection
- Factory classes for LZ4 and Zstd compression algorithms

---
## [0.2.1] - 2025-10-1
### Added
- PipelinesHooks now supports `sessions.get_session_cookies`
- Added `settings.DEDUP_TTL` for automatic key expiration when deduplicating in Redis

## Fixed
- Fixed `ImportError` warning in `scrapy_cffi.utils.fd`

## Removed
- Removed redundant `settings.py` under `scrapy_cffi.models`
- Removed duplicate `KafkaInfo` in `SettingsInfo`
- Removed `RET_COOKIES` from `SettingsInfo`

---

## [0.2.0] - 2025-09-27
### Added
- Redis support single、sentinel、cluster
- Extract dupefilter from the scheduler
- Extension support databases/mq
- Mq module，rabbitmq (70%, aio-pika rpc -> Channel closed by RPC timeout.)
- Mq module，kafka for log
- Session_end must be an independent object
- Command support rabbitmq_spider
- Full bloom dupefilter
- C Extensions support
- SettingsInfo PROJECT_NAME -> QUEUE_NAME
- Deploy basic configuration support

## Fixed
- Request Interceptor behavior bug (return a Response)

---

## [0.1.6] - 2025-09-07
### Added
- Spider hooks get_session_cookies
- Email send util
- StatisticsExtension

## Fixed
- Request Interceptor behavior bug (return a Response)

---

## [0.1.5] - 2025-09-06
### Added
- Initial PyPI release
- CLI change `scrapy-cffi`
- Have a try GitHub Actions workflow for publishing
- Enhance JSON parsing
- Optimize some project structures

## Fixed
- Response selector parsing behavior bug

---
