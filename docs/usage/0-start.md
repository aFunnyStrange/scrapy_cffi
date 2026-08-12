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

# Optional Rust-accelerated Protobuf codec with automatic Python fallback
pip install "scrapy_cffi[protobuf]"
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

Creates a clean project layout. Bloom acceleration is installed through the
optional `scrapy_cffi[bloom]` extra and no longer scaffolds project-local C
binaries. Custom ctypes resources remain available through `cinstall`; see
[12-cpython.md](./12-cpython.md).

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

Framework development has one verification entry point:

```bash
# Rust/Cargo-style test entry
scrapy-cffi test single
scrapy-cffi test sentinel
scrapy-cffi test cluster
scrapy-cffi test all

# Fast daily check without starting Docker
scrapy-cffi test all --quick
```

The full verifier generates all four Demo projects, starts the selected
project-local Docker topologies serially, performs real HTTP/WebSocket crawls,
checks non-persistent cleanup, sends real process interrupts, runs pytest, and
always attempts topology cleanup. It writes `summary.md`, `summary.json`, and
per-phase logs under `artifacts/release-verification/<timestamp>/`.

Use repeated `--mode` options to narrow the matrix, `--no-interrupt` to omit
the interrupt phase, `--log-dir` to select the evidence directory, and
`--keep-workdir` to retain generated projects. Full verification requires its
documented local Docker ports to be available; `--quick` does not use Docker.
Memory is included only in `single`/`all`, because it has no infrastructure
topology.

# 5.infra
Generate an independent local-development Docker Compose stack into `infra/` (or `--output-dir`). It includes Redis, MySQL, PostgreSQL, MongoDB, RabbitMQ, and Kafka; it is deliberately separate from the crawler application image.

```bash
# Generate the single/Sentinel/cluster templates
scrapy-cffi infra generate

# Inspect the exact Compose projects before changing Docker state
scrapy-cffi infra plan --topology cluster --services redis rabbitmq kafka

# Start, inspect, reset, and remove project-local development services
scrapy-cffi infra up --topology single
scrapy-cffi infra status --topology sentinel --services redis
scrapy-cffi infra reset --topology cluster --services redis rabbitmq kafka
scrapy-cffi infra down --topology cluster --services redis rabbitmq kafka

# Remove generated templates; developer-owned infra/.env is preserved
scrapy-cffi infra clean
```

Each generated project records its Compose prefix in
`scrapy_cffi.toml`:

```toml
[default]
project_name = "demo"
infra_project_name = "scrapy_cffi"
```

Compose derives container, network, and volume names from this value and the
selected topology, producing names such as `scrapy_cffi_single` and
`scrapy_cffi_redis_cluster`. During development, change this one prefix and
keep it unique across projects that may run concurrently. Fixed
`container_name` entries are unnecessary and would prevent safe scaling.
This key belongs only to the infra command and generated Docker scripts. The
crawler runtime does not consume it: Redis, databases, RabbitMQ, and Kafka
continue to expose their normal ports, and crawler settings connect to their
ordinary addresses through `REDIS_INFO`, database info, `RABBITMQ_INFO`, and
`KAFKA_INFO`.

For `single`, omitting `--services` starts every service still defined in
`infra/docker-compose.yml`. The generated file initially contains all six
services. You may comment out or remove unneeded service blocks, and may pin or
replace any `image:` entry (including Kafka) in that project-local file.
Routine `infra up/plan/status` fills missing template files without overwriting
those edits. An explicit `infra generate` refreshes generated templates and
should therefore be reviewed like any other scaffold update.

Generated layout:
- `docker-compose.yml`, `.env.example` — independent single-node development infrastructure
- `init.ps1` / `init.sh` — initialize the selected local topology
- `reset.ps1` / `reset.sh` — delete only the current project/topology Compose volumes and recreate it
- `destroy.ps1` / `destroy.sh` — delete that local topology and its volumes without restarting
- `redis-sentinel/`, `redis-cluster/`, `rabbitmq-cluster/`, `kafka-cluster/` — disposable local topology simulations generated by `--all` or individual topology flags
- `production-endpoints.example.toml` — production settings reference for real machine/DNS endpoints

Default disposable-development credentials are recorded in the generated
`infra/README.md`: MySQL uses `root / 123456`, PostgreSQL uses
`postgres / 123456`, and RabbitMQ uses `guest / guest`. Redis, MongoDB, and
Kafka have no authentication. MySQL root host access and unauthenticated
MongoDB are enabled only for this disposable local stack. Initialization
environment variables take effect when a volume is first created, so reset the
affected disposable service after changing them.

Compose project names derive from `default.infra_project_name` plus topology.
Change that TOML prefix to keep concurrently running development projects
separate. `SCRAPY_CFFI_INFRA_PROJECT` / `-ProjectName` can temporarily override
the complete Compose project name when invoking the generated lifecycle
scripts directly.

`startproject` separately generates application-only `docker/Dockerfile`,
`docker/Dockerfile.dockerignore`, and `docker/docker-compose.yml`, with no
database/MQ services and no `depends_on`. Run it with
`docker compose -f docker/docker-compose.yml up`. In production, only the
crawler application is containerized; databases and brokers run on real
machines/native clusters and only their addresses are configured in crawler
settings.

Local multi-port Compose files **only simulate** cluster/sentinel topologies for disposable development and integration testing. They are not production deployment templates.

See also: [11-mq.md](./11-mq.md) for broker settings and integration tests.

# 6.cinstall
Install **user-compiled** ctypes modules into a per-user system directory so every project can load them without copying binaries into each repo.

PyPI packages ship Python wrappers and pure-Python fallbacks only — **not** OS-specific `.dll` / `.so` files.

```bash
# Copy framework template into the current project
scrapy-cffi cinstall --init custom_native

# After building the shared library into cpy_resources/custom_native/build/
scrapy-cffi cinstall custom_native
scrapy-cffi cinstall custom_native --source ./cpy_resources/custom_native --require-binary --force

scrapy-cffi cinstall --list
scrapy-cffi cinstall --path
scrapy-cffi cinstall --remove custom_native
```

Environment: `SCRAPY_CFFI_CPY_DIR` overrides the default system store path.

Details: [12-cpython.md](./12-cpython.md).

# 7.extra
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
