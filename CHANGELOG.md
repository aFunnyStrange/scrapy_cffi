# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Architecture roadmap: [docs/ARCHITECTURE-ROADMAP.md](docs/ARCHITECTURE-ROADMAP.md) · **0.4.3** release: [docs/RELEASE-0.4.3.md](docs/RELEASE-0.4.3.md) · **0.4.2** release: [docs/RELEASE-0.4.2.md](docs/RELEASE-0.4.2.md)

## [0.4.3] - 2026-08-20

### Added

- Per-session request-start rate limits through
  `SESSION_REQUESTS_PER_SECOND` and the session hook API. `None` consistently
  means unlimited, matching the downloader concurrency contract.
- Typed request timeout failures are delivered to Spider errbacks, with
  request-specific retry count and delay overrides.
- Database and message-queue resources are available from every user-editable
  component: Spiders, pipelines, interceptors, extensions, and signal hooks.
- A colored CLI banner displayed only by root `scrapy-cffi -h` and the explicit
  `scrapy-cffi banner` command.

### Changed

- Process-level curl native activation now belongs to
  `scrapy_cffi.platform.curl_native`; request-scoped `impersonate` remains the
  only profile-selection mechanism. `CURL_CFFI_RUNTIME_DIR` is the preferred
  setting and `CURL_CFFI_NATIVE_DIR` remains a compatibility alias.
- The runtime-wide task limit retains its established default of `300`, while
  the downloader-specific `MAX_CONCURRENT_REQ` default remains `None`.
- Redis scheduler persistence stores task state by default. Session cookies and
  client hints require explicit session-persistence opt-in; durable account and
  device data belongs in SQL or another durable user-selected store.
- Pydantic settings accept natural unprefixed `.env` and process-environment
  names such as `TIMEOUT` and `REDIS_INFO__URL`. Existing
  `SCRAPY_CFFI_`-prefixed names remain compatible.
- English and Simplified Chinese documentation now have matching trees, and
  the crawler architecture diagrams were regenerated from corrected sources.

### Fixed

- WebSocket close frames are treated as lifecycle events instead of UTF-8
  business messages, including compatibility across supported `websockets`
  server APIs.
- Downloader stream and WebSocket paths no longer introduce a hidden local
  concurrency cap when `MAX_CONCURRENT_REQ=None`.

FFmpeg multiprocessing is intentionally outside the 0.4.3 scope.

## [0.4.2] - 2026-08-16

### Added

- Integrated the former `curl-cffi-tls-profiles` adapter as
  `scrapy_cffi.profiles`, including ABI-aware external wrapper activation and
  a generic programmatic and manifest-based profile registration API.
- `HttpRequest`, `MediaRequest`, streaming requests, and `WebSocketRequest`
  resolve user-registered aliases through the existing request-scoped
  `impersonate` field; unknown values pass through unchanged.
- `CURL_CFFI_NATIVE_DIR` selects a self-built `_wrapper` plus adjacent native
  libraries at crawler composition time without selecting a global request
  profile. An optional adjacent `scrapy_cffi_profiles.toml` registers only the
  aliases declared by that user-owned build.
- `scrapy-cffi demo -tls` generates a standalone TLS inspection spider, and
  every generated project now includes the user-owned `profiles/` artifact and
  manifest reference structure.
- `WebSocketResponse.stop_listening()` provides explicit, idempotent listener
  shutdown for long-lived connections.

### Changed

- The concrete curl_cffi adapter is now imported lazily so public request and
  spider imports do not make native activation too late.
- Session initialization selects and caches either a direct curl_cffi
  passthrough callback or a registered-alias resolver, avoiding per-request
  feature detection when no custom profiles are configured.
- WebSocket frames are dispatched directly through callbacks and connection
  completion is coordinated by lifecycle events instead of queue end markers.
  Connect and initial send remain one operation; `CloseSignal` stays compatible.
- Engine completion now requires an explicitly completed start producer plus
  zero owned requests. `SCHEDULER_LOOP_END` is deprecated and empty broker
  reads no longer impersonate completion. Queue Spiders expose
  `start_request_limit`; `None` remains a true continuous subscription.
- Release verification now covers real generated Demo projects, finite natural
  exit, and queue consumers that remain alive after work until an explicit
  console stop signal on both Windows and WSL Ubuntu.

## [0.4.1] - 2026-08-15

### Added

- Bloom filtering now uses a stable `xxh3-km-v1` platform contract with
  `fastbloom-rs` PyO3 acceleration from the `bloom` extra and a matching
  pure-Python `ppxxh` fallback. Redis bitmap keys include the algorithm
  version, and native/Python workers are tested for identical indices.
- Kafka Demo projects now generate `scripts/push_kafka_demo.py`, matching the
  RabbitMQ publisher and supporting single or comma-separated cluster bootstrap
  servers for independently verifying start-topic ingestion.
- Optional `pyblackboxprotobuf` Rust acceleration selected once at import
  time, with the bundled `scrapy_cffi.utils.blackboxprotobuf` implementation
  retained as an automatic pure-Python fallback.
- Protobuf platform contracts now include `grpc_encode`,
  `grpc_stream_encode`, and `grpc_decode`; framing semantics remain
  framework-owned while payload encoding/decoding uses the selected backend.
- `scrapy_cffi[protobuf]` installs the qualified native codec explicitly;
  separately installed `pyblackboxprotobuf` packages are detected as well.
- `ProtobufFactory.backend_name()` exposes the active `rust` or `python`
  backend for diagnostics.

### Changed

- Operational settings remain in a single syntax-highlightable `.env` file.
  Nested Pydantic models now serialize as `PARENT__FIELD`, complex lists and
  mappings use indented multiline JSON, and process-level `SCRAPY_CFFI_`
  variables override dotenv and Python defaults. Legacy flat names and compact
  JSON remain readable.
- Bloom defaults now provision 100 million bits for 10 million expected
  values, selecting 7 probes and an estimated 0.82% false-positive rate at
  capacity. Invalid non-positive dimensions are rejected during settings
  validation.
- New projects no longer receive or automatically load the legacy ctypes/FNV
  Bloom scaffold. Generic ctypes templates remain available through explicit
  `cinstall --init` usage.
- Redis Bloom bitmap keys are isolated by the `xxh3-km-v1` algorithm suffix;
  obsolete FNV bitmap keys may be removed after older crawler workers stop.

## [0.4.0] - 2026-08-10

### Added

- Framework-owned async HTTP, WebSocket, cookie-jar, response, stream, and
  session-factory Protocols under `scrapy_cffi.platform`.
- `CurlCffiHttpSession` adapter covering qualified curl_cffi releases from
  0.7.4 through 0.15, including normalized WebSocket lifecycle and failures.
- `HttpRequest(stream=True)`, `StreamResponse`, and bounded `SSEEvent` parsing
  for incremental downloads and AI/chat Server-Sent Event endpoints.
- Framework-owned `WebSocketFlag`; the curl adapter converts it to the vendor
  enum while existing `CurlWsFlag` inputs remain accepted.
- Injectable `HTTP_SESSION_FACTORY` setting for protocol-compatible transports
  and direct test doubles.
- Layered external-resource architecture: parallel Redis, RabbitMQ, Kafka,
  SQLAlchemy, and MongoDB infra clients; repository contracts; and a shared
  resource service/composition root.
- `INFRA_RETRY_ATTEMPTS` and `INFRA_RETRY_DELAY` settings for bounded,
  observable service-layer recovery.

### Changed

- Python 3.9 resolves `curl_cffi>=0.7.4,<0.14`; Python 3.10+ resolves
  `curl_cffi>=0.7.4,<0.16`, allowing 0.14/0.15 without dropping Python 3.9.
- Session management, downloader, robots.txt loading, and FD diagnostics now
  depend on the stable platform contract instead of curl_cffi concrete types.
- Lazy root, utils, config, repository, service, tool, and downloader exports now provide
  explicit type-checking imports so IDE completion/navigation works while
  runtime optional-dependency isolation remains intact.
- Schedulers now depend on `RedisRepositoryProtocol` and
  `RequestQueueRepositoryProtocol`; pipelines, spiders, and extensions receive
  one typed `ResourceService` instead of concrete Manager attributes.
- RabbitMQ/Kafka endpoint models now use the queue-semantic
  `QueueConnectionInfo` and `QueueTopology` names.
- Infrastructure clients execute one operation once. Retry, resource
  replacement, shutdown, and cancellation policy now live above repositories
  in `service/`.

### Fixed

- WebSocket reuse no longer inspects curl_cffi's private `curl._curl` handle,
  which disappeared behind the 0.14/0.15 asynchronous WebSocket rewrite.
- Live streams retain bounded downloader capacity and close on callback
  completion, cancellation, explicit close, or crawler shutdown.

### Removed

- Legacy `scrapy_cffi.databases`, `scrapy_cffi.mq`, and
  `utils.reconnect` implementation modules and their `*Manager` APIs.
- The misleading `infra/broker` grouping; Redis, RabbitMQ, and Kafka are
  parallel external-system adapters because Redis may also carry queued work.

## [0.3.3] - 2026-08-01
### Added
- Shared single-flight reconnect controller for database/MQ adapters. Concurrent
  failures now collapse into one transport rebuild and respect crawler shutdown.
- Cargo-style `scrapy-cffi test single|sentinel|cluster|all` provides the
  single release-check entry for pytest and
  Memory/Redis/RabbitMQ/Kafka crawl/interrupt cases. The verifier continues after individual
  failures, writes Markdown/JSON summaries and per-phase logs, and always
  attempts cleanup. `--quick` provides a Docker-free daily check.
- Generated demos now keep `docker-demo.bat`, `docker-demo.sh`, the manager,
  and the RabbitMQ publisher under `scripts/`; topology/endpoints/mock servers
  live under `demo_support/`. Their
  shared manager supports plan/up/status/reset/down and retained-log
  verification for single-node, Redis Sentinel, and full Redis/MQ cluster
  topologies.
- Demo infrastructure keeps deterministic fixed ports but now preflights all
  ports before Compose startup. Conflicts report the affected service, port,
  Docker container when discoverable, and platform lookup command without a
  Python traceback or partially starting the selected stack.
- Generated Demo managers also provide `verify-interrupt` and
  `verify-interrupt-all`, which send a real process-level console interrupt and
  retain cleanup evidence for every supported topology.
- `scrapy-cffi infra` unifies local template generation, Compose planning,
  configuration, startup, status, reset, shutdown, destruction, and cleanup by
  topology and service.
- `KafkaSpider` / `KafkaScheduler` with separate start and work topics, compressed request payloads, Redis-backed dedup/session state, and manual contiguous offset commits.
- Persistent Session Cookie Hash state and adaptive request-state compression.
- Independent `infra` development stack for Redis, MySQL, PostgreSQL, MongoDB,
  RabbitMQ, and Kafka, with PowerShell/shell lifecycle scripts.
- Local simulations for Redis Sentinel/Cluster, RabbitMQ Cluster, and Kafka
  Cluster. Compose project names derive from crawler project + topology,
  isolating containers, networks, and volumes across projects.
- `production-endpoints.example.toml` and production connection settings for real infrastructure hosts: Redis ACL/Sentinel auth/TLS/timeouts/address remap, RabbitMQ timeout/heartbeat, and Kafka SASL/TLS/client timeout.

### Changed
- Constrain `curl_cffi` to the currently qualified range
  `>=0.7.4,<=0.13.0`; 0.15.0 remains excluded pending an upstream API
  compatibility review of the HTTP and WebSocket adapters.
- Expand CI coverage to full-feature Python 3.9 through 3.13 environments and
  a Python 3.14 core-package smoke test. Python 3.9 tests no longer rely on
  Python 3.10-only temporary-directory or event-loop behavior.
- New projects persist the editable Compose prefix
  `default.infra_project_name = "scrapy_cffi"` in `scrapy_cffi.toml`;
  developers change this one value and keep it unique across concurrently
  running projects. Single-node startup now delegates an omitted service list to Compose, so the project-local
  `infra/docker-compose.yml` is the source of truth for enabled services and
  image versions. Normal infra operations fill missing templates without
  overwriting developer image/service edits.
- `startproject` now groups application-only container artifacts under
  `docker/` (`Dockerfile`, `Dockerfile.dockerignore`, and Compose file), keeping
  the generated project root focused on crawler code.
- Optional transports/databases now have declared installation extras
  (`rabbitmq`, `kafka`, `mysql`, `postgres`, and `mongodb`). Generated
  RabbitMQ/Kafka demos select the matching extra in `requirements.txt`.
- Local database credentials now follow their common image defaults: MySQL
  `root / 123456`, PostgreSQL `postgres / 123456`, and unauthenticated MongoDB.
  Generated infra documentation lists every default single-node credential;
  these relaxed settings are limited to disposable development stacks.
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
  `PRECONDITION_FAILED`; message delivery mode and shutdown cleanup still
  follow `SCHEDULER_PERSIST`.
- RabbitMQ queue declarations are now stable (`durable=True`,
  `auto_delete=False`) across ingress publishers and crawler persistence modes.
  `SCHEDULER_PERSIST` controls message delivery mode and shutdown cleanup, so
  switching the flag no longer closes the channel with queue
  `PRECONDITION_FAILED`.
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
- Redundant `geninfra`/`verify` CLI aliases, root verification wrappers, and
  duplicate verification scripts; `scrapy-cffi infra` and
  `scrapy-cffi test` are now the only supported entry points.
- Committed generated Demo/log artifacts, duplicate broker Compose stacks,
  abandoned test projects/workflows, and cached bytecode. Runtime verification
  evidence remains local under the ignored `artifacts/` directory.
- The obsolete demo README and monolithic project Compose database/MQ definitions. Generated demos now use the topology-aware local-infra guide.

### Fixed
- Ctrl+C now cancels active work before broker shutdown, requeues unfinished Redis/RabbitMQ requests, leaves Kafka offsets uncommitted, and snapshots Session cookies before Redis writes are disabled.
- Non-persistent Redis cleanup now runs before the global stop flag and
  independently from RabbitMQ/Kafka cleanup. A broker cleanup failure can no
  longer skip dedup/session key deletion, and failed cleanup is retried once by
  the idempotent shutdown path.
- RabbitMQ dequeue uses cancellation-safe, shielded short polling. Ctrl+C no
  longer cancels aio-pika's in-flight `Basic.Get` RPC, corrupts the channel, or
  loses a delivery that raced with shutdown.
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
- Redis Cluster routing now normalizes enum modes, uses one hash tag for
  multi-key Lua operations, avoids blocking start-request starvation, and
  announces Docker node hostnames that the generated client remaps locally.
- RabbitMQ cluster consumption now uses independent queue consumer channels,
  preventing long-polling start/work queues from starving publishing on the
  shared management channel.
- Kafka topic creation now waits for every partition leader to enter ISR before
  admitting producers/consumers, without blocking an existing under-replicated
  topic that still has a valid leader; cluster healthchecks also include the
  consumer group coordinator. Kafka/Redis ingress child tasks are now always
  cancelled and awaited during shutdown.
- Generated Windows runners register SIGINT/SIGBREAK and route Ctrl+C or
  Ctrl+Break through the same idempotent `crawler.shutdown()` path used on
  POSIX.

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
