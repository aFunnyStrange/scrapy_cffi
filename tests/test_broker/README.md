# Broker Integration Tests

Unified broker tests for `scrapy_cffi` modules (since **0.3.0**):

- Redis: `single` / `sentinel` / `cluster` (real CRUD)
- RabbitMQ: `single` / `cluster` (queue CRUD-style flow)
- Kafka: `single` / `cluster` (event-based CRUD semantics)

Related docs: [`docs/usage/11-mq.md`](../../docs/usage/11-mq.md) · [`docs/usage/1-settings.md`](../../docs/usage/1-settings.md) (broker + `REDIS_STREAM_INFO`).

To scaffold your own compose files (baseline + optional topology subdirs), use `scrapy-cffi geninfra` — see [`docs/usage/0-start.md`](../../docs/usage/0-start.md#5geninfra).

All commands below use Linux shell style (`bash`).

## 1) Start broker containers

### Redis Sentinel

```bash
docker compose -f tests/test_broker/stacks/redis/sentinel/docker-compose.yml up -d
```

### Redis Cluster

```bash
docker compose -f tests/test_broker/stacks/redis/cluster/docker-compose.yml up -d
```

### RabbitMQ Cluster

```bash
docker compose -f tests/test_broker/stacks/rabbitmq/docker-compose.yml up -d
```

### Kafka Cluster

```bash
docker compose -f tests/test_broker/stacks/kafka/docker-compose.yml up -d
```

## 2) Run broker tests

From repo root:

```bash
python tests/test_broker/test_redis_broker.py sentinel
python tests/test_broker/test_redis_broker.py cluster
python tests/test_broker/test_rabbitmq_broker.py cluster
python tests/test_broker/test_kafka_broker.py cluster
```

Single mode remains the normal default path; no extra mandatory smoke run is required:

```bash
python tests/test_broker/test_redis_broker.py single
python tests/test_broker/test_rabbitmq_broker.py single
python tests/test_broker/test_kafka_broker.py single
```

## 3) Config templates

See:

- `tests/test_broker/config_templates.toml`
- `tests/test_broker/docker-compose.single.example.yml`

These provide framework connection templates for single/sentinel/cluster and a single-node local compose baseline.

Map values into `settings.REDIS_INFO`, `settings.RABBITMQ_INFO`, and `settings.KAFKA_INFO`. For RedisSpider stream ingress (optional), see `settings.REDIS_STREAM_INFO` in docs.

## 4) Local simulation vs production

Current docker files in `tests/` are for local validation on one machine (multi-container, multi-port).
They validate framework integration logic, not full production orchestration.

For real production (typically one Redis/RabbitMQ/Kafka node per host), you should additionally implement:

- host-level networking and service discovery (DNS/LB), not `host.docker.internal`
- TLS, auth, ACL, secrets management, and cert rotation
- persistence sizing (disk IOPS/capacity), backup and restore drills
- anti-affinity and fault-domain placement (rack/zone/region)
- resource limits/requests and rolling upgrade strategy
- observability (metrics, logs, alerts) and SLO-based capacity controls

So: **yes**, production docker/k8s configs are usually much more complex than local templates.
These templates are an integration baseline to verify `scrapy_cffi` connectivity first.
