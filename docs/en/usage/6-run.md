# 1.Introduction
`scrapy_cffi` is a fully asynchronous web crawling framework for Python. It does **not** support `scrapy`-style CLI commands such as `scrapy crawl ...`.

Because the framework is built on top of Python's `asyncio`, it follows a centralized event loop principle. This means certain exceptions (like keyboard interrupts) can only be handled at the top-level loop. To accommodate different usage scenarios, the framework provides two modes: **Standard User Mode** and **Advanced User Mode**.


---


# 2.Standard User Mode
In most use cases, you can simply use the synchronous interfaces run_spider_sync or run_all_spiders_sync. These are plug-and-play APIs that automatically create and run the event loop internally, allowing you to start spiders without dealing with asynchronous logic.


---


# 3.Advanced User Mode
If you need fine-grained control (e.g., integrating with an existing multithreaded, multiprocess, or asynchronous system), you can use the asynchronous versions `run_spider` and `run_all_spiders` directly.

When working with custom event loops (`new_loop`), be aware of potential risks related to sharing objects across loops—manual handling is required.

⚠️ **Notes:**
- The framework provides built-in **thread-level logging**. If you require **process-level logging**, ensure that multiple processes do not write to the same log file concurrently.
- The framework only provides reference implementations; advanced users must manage logging and system resources appropriately.

```python 
from scrapy_cffi.utils import start_multiprocess_log_listener, init_logger_multiprocessing
```


---


# 4.Additional Information
## 4.1 ❓ **Why is there no global `settings.py`?**
Unlike `Scrapy`, which typically launches one spider per process, `scrapy_cffi` allows multiple spiders to run within a single process. Defining a global configuration file (like `settings.py`) can lead to unintended side effects—such as overriding parent-level or scheduler-wide configurations—especially when spiders are used as downstream components in a centralized system.

To avoid such conflicts, `scrapy_cffi` uses explicit settings injection: configuration must be passed as arguments when launching spiders. This ensures that spiders remain isolated and do not affect the global context. Additionally, it enables easy batch construction of multiple spiders, each with its own customized settings.

🔧 **Utilities & API Helpers**
`scrapy_cffi.utils` provides a set of utility functions to simplify common tasks, especially for users transitioning from Scrapy or integrating with legacy configurations:
**1.to_scrapy_settings_py(settings_obj)**
Converts a `SettingsInfo` object into a Scrapy-style `settings.py` string. (You must write it to a file manually.)

**2.load_settings_from_py(filepath: str, auto_upper=True)**
Loads settings from a Scrapy-style `settings.py` file.

**3.convert_to_toml(py_path: str, toml_path: str)**
Converts `settings.py` to `.toml` format.

**4.ScrapyRunner、InlineScrapyRunner**
Launches a Scrapy project via subprocess using a Python script. Useful for hybrid scheduling.

## 4.2 scrapy_cffi design idea
The lifecycle of a single spider follows an event-driven request, response, and
item flow. See the [single-spider lifecycle](../../assets/diagrams/spider-lifecycle.svg).

Each spider is bound to its own **Engine** and scheduler, while runtime
components such as the downloader, interceptor chains, pipelines, signals, and
resource service are shared by the top-level `Crawler`. See the current
[Crawler structure](../../assets/diagrams/crawler-structure.svg).

When running `run_all_spiders`, all spiders execute within the **same thread and event loop**, allowing seamless integration with external asyncio-based systems or frameworks. This shared-loop design keeps things simple and efficient for standard use cases.

Each spider still retains its own Engine and scheduler semantics. A finite
spider can complete while a Redis/RabbitMQ/Kafka sibling continues listening,
so the shared Crawler remains alive. A normal `Spider` also keeps the in-memory
`Scheduler`; it is not implicitly promoted by a distributed sibling. Configure
`settings.SCHEDULER` explicitly only when one scheduler class should override
all spiders.

For isolated settings and resources on the same event loop, use `run_spiders`
to create multiple `Crawler` instances. Use a thread or process boundary only
when a separate event loop or process is actually required. See the
[orchestration modes](../../assets/diagrams/orchestration.svg).

This design allows `scrapy_cffi` to adapt cleanly to both **monolithic** and **distributed** usage patterns.

Note on **High Concurrency / Cluster Mode**
For extremely high concurrency workloads, run multiple workers against shared
broker ingress and a namespaced deduplication store. See the
[cluster deployment](../../assets/diagrams/cluster-deployment.svg).

**Local infra scaffolding:** run `scrapy-cffi infra generate`, then use
`scrapy-cffi infra up/reset/down --topology ... --services ...`. These stacks
are local simulations only; production connects the crawler container directly
to real database/MQ machines. Details: [0-start.md](./0-start.md#5infra),
[11-mq.md](./11-mq.md).

**Multiple crawlers on one loop:** `run_spiders` / `run_spiders_sync` — see [14-multi-spider-resources.md](./14-multi-spider-resources.md).

**Standalone tools (no crawl loop):** [13-standalone-tools.md](./13-standalone-tools.md).

**Deduplication (Redis / Bloom / cluster routing):** [15-deduplication.md](./15-deduplication.md).
