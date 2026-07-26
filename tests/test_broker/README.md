# Broker integration tests

These opt-in tests exercise real Redis, RabbitMQ, and Kafka endpoints:

- Redis: single, Sentinel, and Cluster
- RabbitMQ: single and cluster
- Kafka: single and cluster

The repository has one source of Docker topology definitions:
`scrapy_cffi/templates/infra/` and `scrapy_cffi/templates/topologies/`.
Generate a disposable local stack instead of maintaining duplicate test
Compose files:

```bash
scrapy-cffi infra generate
scrapy-cffi infra up --topology single --services redis rabbitmq kafka
scrapy-cffi infra up --topology sentinel --services redis rabbitmq kafka
scrapy-cffi infra up --topology cluster --services redis rabbitmq kafka
```

Run an individual integration script from the repository root:

```bash
python tests/test_broker/test_redis_broker.py single
python tests/test_broker/test_redis_broker.py sentinel
python tests/test_broker/test_redis_broker.py cluster
python tests/test_broker/test_rabbitmq_broker.py single
python tests/test_broker/test_rabbitmq_broker.py cluster
python tests/test_broker/test_kafka_broker.py single
python tests/test_broker/test_kafka_broker.py cluster
```

Connection endpoints can be overridden with the environment variables
documented at the top of each script. Remove the disposable infrastructure
when finished:

```bash
scrapy-cffi infra down --topology single --services redis rabbitmq kafka
scrapy-cffi infra down --topology sentinel --services redis rabbitmq kafka
scrapy-cffi infra down --topology cluster --services redis rabbitmq kafka
```

These stacks are development simulations. Production crawlers connect directly
to independently deployed infrastructure using `RedisInfo`, `RabbitMQInfo`,
and `KafkaInfo`.
