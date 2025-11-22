# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
None

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
