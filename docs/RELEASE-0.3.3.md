# scrapy_cffi 0.3.3

Released: 2026-08-01

Version 0.3.3 strengthens restart-safe distributed crawling, local
infrastructure verification, and the package release boundary.

## Highlights

- Redis, RabbitMQ, and Kafka schedulers support controlled shutdown and
  non-persistent state cleanup, including process interrupts.
- RabbitMQ and Kafka request queues retain Redis-backed distributed
  deduplication; Kafka separates start requests from incremental requests.
- Persisted session cookies and request state use bounded serialization and
  compression to reduce Redis memory pressure.
- Database and MQ reconnect handling uses explicit, IDE-visible manager APIs
  with shared single-flight transport recovery.
- `scrapy-cffi infra` manages disposable single, Sentinel, and cluster
  development topologies independently from production crawler deployment.
- `scrapy-cffi test single|sentinel|cluster|all` provides repeatable Demo,
  interrupt, cleanup, and retained-log verification.
- Generated projects keep application Docker files and infra tooling in
  dedicated directories, with Compose resource isolation configured through
  `scrapy_cffi.toml`.

## Compatibility and packaging

- Python 3.9 through 3.13 are tested with all declared database and broker
  extras. Python 3.14 passes the core and non-MySQL matrix; MySQL remains
  provisional until `asyncmy` provides a compatible tested distribution.
- `curl_cffi` is constrained to the qualified range
  `>=0.7.4,<=0.13.0`; compatibility with 0.15.0 will be reviewed separately.
- The GitHub Actions release pipeline verifies tag/version agreement, tests
  source and built distributions, checks Twine metadata, preserves immutable
  artifacts between jobs, and publishes from a dedicated PyPI job.

See [CHANGELOG.md](../CHANGELOG.md) for the complete list of changes and
[ARCHITECTURE-ROADMAP.md](ARCHITECTURE-ROADMAP.md) for architectural status.
