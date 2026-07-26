# Tests

The default suite contains framework unit and smoke tests:

```bash
python -m pytest -q
```

Key coverage:

- scheduler persistence, request serialization, Cookie restoration, and Ctrl+C
  shutdown behavior;
- Redis ingress and distributed deduplication isolation;
- RabbitMQ and Kafka request schedulers;
- database/MQ reconnect controllers;
- generated project, Demo, Docker, and infrastructure templates;
- Python 3.9 syntax and annotation compatibility.

`test_broker/` contains opt-in tests against live Redis, RabbitMQ, and Kafka.
Generate their disposable infrastructure from the canonical templates:

```bash
scrapy-cffi infra generate
scrapy-cffi infra up --topology single --services redis rabbitmq kafka
```

See [test_broker/README.md](test_broker/README.md) for topology-specific runs.
Database integration tests use their corresponding environment variables and
skip when the optional driver or live endpoint is unavailable.

The complete generated-Demo matrix is exposed through one CLI:

```bash
scrapy-cffi test single
scrapy-cffi test sentinel
scrapy-cffi test cluster
scrapy-cffi test all
scrapy-cffi test all --quick
```

Verification logs are written below the ignored `artifacts/` directory.
