# 1.Introduction
`scrapy_cffi` includes a user-friendly command-line interface (CLI) that allows you to quickly scaffold a new project or generate spiders.
While the default structure is designed to be practical out of the box, you're encouraged to adapt it to suit your own development needs.

**Notes:**
> The CLI command is `scrapy_cffi` in versions ≤0.1.4 and `scrapy-cffi` in versions >0.1.4 for **improved usability**.

> **From 0.3.0**, core framework changes are developed with AIGC-assisted workflows. For the latest features before PyPI catches up, install from GitHub or source (see below).

# 1.1 Installation

#### From PyPI
```bash
pip install scrapy_cffi
```

#### From GitHub (latest main)
```bash
python -m pip install "scrapy_cffi @ git+https://github.com/aFunnyStrange/scrapy_cffi.git"
```

#### From source (development)
```bash
git clone https://github.com/aFunnyStrange/scrapy_cffi.git
cd scrapy_cffi
pip install -e .
```

# 2.startproject
```bash
scrapy-cffi startproject <project_name>
```

---



# 3.genspider
> After startproject <project_name>
## 3.1 Spider
```bash
cd <project_name>
scrapy-cffi genspider <spider_name> <domain>
```

## 3.2 RedisSpider
```bash
cd <project_name>
scrapy-cffi genspider -r <spider_name> <domain>
```

## 3.3 RabbitmqSpider
RabbitmqSpider has higher priority than RedisSpider. By default, it still uses Redis for deduplication.
```bash
cd <project_name>
scrapy-cffi genspider -m <spider_name> <domain>
```

---



# 4.demo
> If you need to refer to the demo project.
## 4.1 Spider
```bash
scrapy-cffi demo
```

### 4.2 RedisSpider
```bash
scrapy-cffi demo -r
```

### 4.3 RabbitmqSpider
```bash
scrapy-cffi demo -m
```

# 5.geninfra
Generate Docker Compose infrastructure templates (Redis / RabbitMQ / Kafka topologies) into a local `infra/` directory (or `--output-dir`).

```bash
# Baseline single-node stack (docker-compose.yml + Dockerfile)
scrapy-cffi geninfra

# Also emit optional override templates for non-single modes
scrapy-cffi geninfra --redis cluster --rabbitmq cluster --kafka cluster

# Baseline only, no topology subdirs
scrapy-cffi geninfra --all

# Remove previously generated artifacts
scrapy-cffi geninfra --clean
```

Generated layout:
- `docker-compose.yml`, `Dockerfile` — single-node baseline
- `redis-sentinel/`, `redis-cluster/`, `rabbitmq-cluster/`, `kafka-cluster/` — optional override stacks
- `topology.example.toml` — fill in hosts/ports for your environment

Local multi-port compose files **simulate** cluster/sentinel topologies for development; production multi-host orchestration is still your responsibility.

See also: [11-mq.md](./11-mq.md) for broker settings and integration tests.

# 6.extra
In real-world development, spiders are usually integrated with backend systems. `scrapy_cffi` only provides the core crawling system, while additional components such as message queues (MQ) and task schedulers (e.g., Celery) should be configured by users according to their own requirements.

**⚠️ Important Note:**
`Celery` runs as a standalone process started from the command line.
If you try to directly start a `scrapy_cffi` spider inside `Celery` code, it may lead to incorrect import paths.

**✅ Recommended Approach:**
Let the `backend` push task messages → `Celery` distributes them to specific `Redis` keys → `scrapy_cffi’s` RedisSpider consumes those keys and runs the spider accordingly. For details, refer to [system](https://github.com/aFunnyStrange/scrapy_cffi/blob/main/docs/images/system.jpg).



# 7.Issues
## 7.1 Unclean shutdown on Ctrl+C
In certain cases, when stopping the crawler with `Ctrl+C`, Python may display harmless exceptions such as:
```python
Task was destroyed but it is pending!
RuntimeError: Event loop is closed
```

This behavior is a known side effect of Python’s asynchronous event loop.
Since task cancellation in asyncio is cooperative, some background tasks may still be pending when the event loop closes, producing these warnings.

The framework ensures that all managed resources are properly released, but console output may not always be perfectly clean.

Contributions or suggestions to improve shutdown handling and minimize these messages are welcome.