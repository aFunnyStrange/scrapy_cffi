# tests/

Integration and smoke tests for `scrapy_cffi`. For development, install from source or GitHub (see root [`README.md`](../README.md)); **≥ 0.3.0** changes are AIGC-assisted and may land on GitHub before PyPI.

## Broker (Redis / RabbitMQ / Kafka)

Primary entry: [`tests/test_broker/README.md`](test_broker/README.md)

- Scripts: `test_redis_broker.py`, `test_rabbitmq_broker.py`, `test_kafka_broker.py`
- Stacks: `test_broker/stacks/{redis,rabbitmq,kafka}/`
- Config templates: `test_broker/config_templates.toml`

Legacy dirs `tests/test_redis`, `tests/test_rabbitmq`, and `tests/test_kafka` were removed in **0.3.0** — use `test_broker` instead.

Local infra scaffolding (alternative to test stacks): `scrapy-cffi geninfra` → see [`docs/usage/11-mq.md`](../docs/usage/11-mq.md).

## Databases

| Test | Requires |
| ---- | -------- |
| [`test_mysql.py`](test_mysql.py) | MySQL + `sqlalchemy[asyncio]` |
| [`test_mongodb.py`](test_mongodb.py) | MongoDB + `motor` |
| [`test_postgres/test_postgres_manager.py`](test_postgres/test_postgres_manager.py) | PostgreSQL + `asyncpg` |

## Framework units (no live broker)

| Test | Covers |
| ---- | ------ |
| [`test_redis_ingress.py`](test_redis_ingress.py) | `REDIS_STREAM_INFO` / spider attr merge |
| [`test_dupefilter_fingerprint.py`](test_dupefilter_fingerprint.py) | URL query param order in dedup fingerprint |

## Other

- [`c_bloom/readme.md`](c_bloom/readme.md) — C Bloom filter build notes
- [`blackboxprotobuf/`](blackboxprotobuf/) — protobuf helper tests
- [`unstable_workflows/`](unstable_workflows/) — release/changelog CI scripts

Docs index: [`docs/usage/`](../docs/usage/).
