# 1.Introduction
`scrapy_cffi` uses `pydantic v2` to define its `SettingsInfo` class.  
This approach ensures:

- Strong typing and IDE-friendly autocompletion.
- Default values and runtime validation for each setting.
- Prevention of misconfigured or mistyped settings.

If you prefer a more Scrapy-like `settings.py`, scrapy_cffi does not support CLI-based settings.py export 
because settings are dynamically created via functions and may depend on runtime context or parameters. But you can call:
``` python 
from scrapy_cffi.utils import to_scrapy_settings_py
from my_project.settings import create_settings

# Create your SettingsInfo instance — arguments are flexible and project-specific
settings = create_settings(
    spider_path="./spiders", 
    user_redis=True,
    # ... other args/kwargs ...
)
to_scrapy_settings_py(settings)
```

When you create a project using `scrapy_cffi` CLI, the generated `settings.py` includes:
- An `env_path` variable pointing to your `.env` file.
- Functions `settings_to_env` and `env_to_settings` for converting between **Pydantic SettingsInfo objects** and **.env configuration files**.

This feature allows developers to:
- Develop using native Python objects with full type hints and IDE autocompletion.
- Seamlessly convert between `SettingsInfo` instances and `.env` files for **easy deployment and operational configuration**.
- Implement a **one-click development-to-deployment workflow**, where settings can be versioned, validated, and reused across environments.

---





# 2.SettingsInfo
## 2.1 General Settings
### 2.1.1 MAX_GLOBAL_CONCURRENT_TASKS
- **Type**: Optional[Union[int, None]]
- **Default**: 300
- **Description**: Defines the maximum number of concurrent asynchronous tasks allowed globally within a single crawler engine instance. When set to an integer, a global `BoundedSemaphore` is enabled to throttle overall task concurrency—including HTTP requests, WebSocket listeners, scheduler operations, and pipeline processing. When set to `None`, no global concurrency restriction is enforced, allowing the engine to freely schedule all tasks.

**Design Rationale**
Each running spider in this framework is managed by its own dedicated engine instance. Within each engine, task scheduling is fully asynchronous: requests from the scheduler, middleware processing, downloading, and spider callbacks are all submitted as non-blocking `asyncio` tasks. This design maximizes performance and responsiveness.

However, on certain platforms—especially **Windows**—the underlying asyncio event loop has a limited capacity for open file descriptors and concurrent coroutines. Without global throttling, mass task creation may result in runtime errors such as:

```python
ValueError: too many file descriptors in select()
```

**Platform-Specific FD Limits:**
- **Windows**: Each process has a default C runtime (CRT) file descriptor limit, typically **512**. Newer CRT versions may allow this limit to be increased up to **8192** using `_setmaxstdio()`, but this adjustment:
    - Only affects the current process
    - Is not guaranteed to be available in all Python distributions

- **Linux/macOS**: Each process’s file descriptor limit is controlled by the operating system via `ulimit` or `resource.RLIMIT_NOFILE`. Soft limits can be temporarily increased within the hard limit, but system-imposed hard limits still apply. High-performance event loops like `uvloop` reduce select/poll limitations, but FD exhaustion is still possible at extremely high concurrency.

**FD Monitoring Utility:**
A cross-platform utility class, FDUtil, is provided to help developers monitor file descriptor usage:
- `FDUtil.get_max_fd()` – returns the maximum number of file descriptors / handles available to the current process
- `FDUtil.get_used_fd()` – returns the number of file descriptors / handles currently in use

Example usage:
```python
from scrapy_cffi.utils import FDUtil

max_fd = FDUtil.get_max_fd()
used_fd = FDUtil.get_used_fd()
print(f"Max FD: {max_fd}, Used FD: {used_fd}")

FDUtil.print_fd_info()
```

**Important Notes:**
1. `FDUtil` **only provides read-only information**. It does not provide any method to increase system or CRT limits.

2. **Python-level modification of system FD limits is generally not feasible:**
- Windows: `_setmaxstdio()` may increase the CRT limit, but availability is not guaranteed
- Linux/macOS: Python can only adjust soft limits within the system hard limit

3. `FDUtil` is intended as a **monitoring and guidance tool**, allowing developers to configure the crawler engine’s global concurrency semaphore safely.

**Practical Recommendation:**
Even on Linux/macOS, where `MAX_GLOBAL_CONCURRENT_TASKS = None` theoretically allows unlimited task scheduling, it is **strongly recommended to set a reasonable global concurrency limit based on empirical observations:**
- Prevents resource exhaustion (FDs, sockets, memory)

- Ensures stable and predictable performance across environments

- Acts as the **first layer of defense**, complementing component-level concurrency controls like downloader limits, pipeline batching, or scheduler throttling

**Mechanism:**
This global lock is shared across all internal components and applied at key task creation points using `async with global_lock()`:, ensuring that only a limited number of tasks are active at any moment.

--- 

### 2.1.2 QUEUE_NAME
- **Type**: Optional[Union[str]]
- **Default**: ""
- **Description**: The queue for requested objects shared by all spiders. In most cases, explicit configuration is **not required**. If configured, all requested objects will share this queue in `run_all_spiders` mode. Attention should be paid to **potential competition** among multiple spiders in the same scheduler.

**Background and Purpose**
Originally, this configuration was implemented to support **distributed queues**. However, after design considerations, it became clear that:

- `QUEUE_NAME` is **only meaningful in `run_spider` mode**.
    - In this mode, multiple instances of the **same spider** in a distributed environment can share a queue by specifying the same `QUEUE_NAME`.
    - If not specified, the framework defaults to a queue named `f'{spider_name}_req'`.

- In `run_all_spiders` mode, different types of spiders typically use **separate queues**, so `QUEUE_NAME` should generally **not** be set.

---

**Special Case: WebSocket Spiders**
- WebSocket connections are **long-lived, bidirectional, and stateful**.

- Regardless of `run_spider` or `run_all_spiders`, once a WebSocket task is assigned, it should be considered handled by a single spider.

- Attempting to distribute WebSocket messages across multiple spiders in a queue may result in:
    - Loss of WebSocket connection context in the scheduler.
    - Erratic behavior where some spiders never receive the stop signal, causing indefinite listening.

- Therefore, in a distributed WebSocket setup, the **stop signal** should be explicitly provided by the user. Sharing a stop signal via a common queue can easily cause scheduling conflicts.

---

**Summary of Potential Use Cases for `QUEUE_NAME`**
- **Custom request queues**: Users can override the default `f'{spider_name}_req'` queue if their workflow requires a specific queue naming convention.

- **Distributed WebSocket spiders**:
    - Assigning a specific `QUEUE_NAME` ensures that all tasks are routed to the intended spider without competing for the default queue.
    - Alternatively, this can be achieved by modifying `spider_name` to implicitly generate separate queues.

---

### 2.1.3 ROBOTSTXT_OBEY
- **Type**: Optional[bool]
- **Default**: True
- **Description**: Whether to respect the website’s robots.txt rules.
If set to True, the crawler will skip URLs disallowed by robots.txt.

---

### 2.1.4 MAX_SCHEDULER_LOOP_NUM
- **Type**: Optional[int]
- **Default**: 10
- **Description**: defines how many concurrent scheduler consumer loops (workers) the engine should create.
Each worker continuously pulls requests from the scheduler and executes the full processing pipeline independently.
This value directly determines the framework’s concurrency level.

**Note:**
In a `single Crawler` scenario, when using the `run_all_spiders` mode to start multiple spiders, each spider corresponds to an Engine, and **each Engine creates self.settings.MAX_SCHEDULER_LOOP_NUM scheduler_loop**. By default, **end_count (i.e., SCHEDULER_LOOP_END) is None**, meaning the loops continuously listen to the queue. Under these conditions, `aio_pika.connect_robust` may raise errors. This is fundamentally due to limitations in aio_pika's underlying connection pool implementation. While multiple scheduler_loop instances are used to increase concurrency under high task load, aio_pika does not fully support a large number of concurrent robust connections.


**Impact on Performance**

A higher value can increase throughput when the spider has enough pending requests.
However, setting this value too high may reduce performance under light workloads:

Too many idle workers increase task scheduling overhead.

The event loop spends more time waking, parking, and switching between workers.

CPU time may be wasted on workers that have no work to perform.

Actual task processing can become slower than with fewer workers.

In short:
> **More workers ≠ always faster.**
> Worker count should match the expected workload.



**Why the Framework Does Not Auto-Scale Workers**

This framework intentionally forbids automatic worker expansion or reduction.

**Reason 1 — Canceling workers is unsafe**
A worker may currently be:
- holding a request,
- inside middleware,
- downloading,
- or running spider callbacks.
Force-canceling it can drop the in-flight request, which violates the framework's design principle:

**“No request should be lost due to internal worker cancellation.”**

**Reason 2 — Auto-scaling makes the system non-deterministic**
Dynamic cancellation introduces unpredictable race conditions and debugging difficulty.
Fixed workers ensure stable and repeatable scheduling behavior.

**Reason 3 — Concurrency must be user-defined**
Worker count reflects how aggressively requests should be processed.
It must be configured explicitly by the user based on machine resources and spider design.

For these reasons, the framework always uses a **fixed-size worker pool**, with no auto-scaling.



**Notes**
- Workers are persistent and run for the entire lifetime of the engine.
- No recursive task creation occurs, preventing coroutine tree explosion.
- Too few workers lowers concurrency; too many workers increase scheduling overhead.
- Adjust according to workload and system resources.

| **Worker Count** | **Workload** |     **Expected Effect**      |
| ---------------- | ------------ | ---------------------------- |
|       Low        |     Heavy    |       Bottleneck / slow      |
|       High       |     Heavy    |        Good throughput       |
|       High       |     Light    | Slower due to overscheduling |
|  Extremely High  |      Any     |       Event-loop thrash      |

---

### 2.1.5 SCHEDULER_LOOP_END
- **Type**: Union[int, None]
- **Default**: None
- **Description**: For terminable spiders using `RedisScheduler`, `RabbitMqScheduler`, or other custom schedulers in `scrapy-cffi >= 0.2.5`, this setting allows controlling the number of scheduler loops before the program exits automatically.
    - If `None` (default), the scheduler continues listening indefinitely.
    - Only set this for finite/terminable spiders.
    - Continuous-listening spiders (e.g., `RedisSpider` + `RedisScheduler`, `RabbitMqSpider` + `RabbitMqScheduler`, or other custom persistent spiders) should **not** configure this option.


---

## 2.2 Request
### 2.2.1 USER_AGENT
- **Type**: Optional[str]
- **Default**: "scrapy_cffiBot"
- **Description**: Global User-Agent setting.
If a request does not explicitly specify a User-Agent header, this value will be automatically applied.

---

### 2.2.2 DEFAULT_HEADERS
- **Type**: Optional[Dict]
- **Default**: {}
- **Description**: Default headers to apply when a request does not specify any.

---

### 2.2.3 DEFAULT_COOKIES
- **Type**: Optional[Dict]
- **Default**: {}
- **Description**: Default cookies to apply when a request does not specify any.

---

### 2.2.4 MAX_CONCURRENT_REQ
- **Type**: Optional[int]
- **Default**: None
- **Description**: Maximum number of concurrent requests handled by the downloader. This setting only applies to the downloader itself—it does **not** restrict schedulers, middleware chains, or spider callbacks. When set to an integer, it limits how many requests can be downloaded in parallel. When set to `None`, the downloader does **not** apply any internal concurrency restriction.

Internally, this uses either `asyncio.Semaphore` or `asyncio.BoundedSemaphore`, depending on the `USE_STRICT_SEMAPHORE` setting (see below for details).

**Important Note**  
This setting operates in conjunction with the global task limiter `MAX_GLOBAL_CONCURRENT_TASKS`. Even if `MAX_CONCURRENT_REQ` is set to a large value (or `None`), the **effective concurrency will never exceed the global task limit**. The downloader must acquire the global lock **in addition to** its local semaphore before dispatching a request.

This ensures that download pressure cannot destabilize the framework on platforms with low system-level coroutine capacity (e.g., Windows), and also maintains fairness across multiple components (e.g., Redis IO, WebSocket listeners, spider parsing) that share the same global task pool.

---

### 2.2.5 USE_STRICT_SEMAPHORE
- **Type**: Optional[bool]
- **Default**: False
- **Description**: Controls how strictly the downloader enforces the `MAX_CONCURRENT_REQ` limit. If set to `False`, the downloader uses `asyncio.Semaphore`, which limits only the number of **active downloading tasks**, while allowing more tasks to be submitted and queued internally. If set to `True`, it uses `asyncio.BoundedSemaphore`, which strictly limits the number of tasks that can be **submitted to the downloader** at all — any excess will be blocked or deferred in the engine. This setting has no effect unless `MAX_CONCURRENT_REQ` is set.

---

### 2.2.6 TIMEOUT
- **Type**: Optional[int]
- **Default**: 30
- **Description**: Maximum request timeout in seconds.

---

### 2.2.7 MAX_REQ_TIMES
- **Type**: Optional[int]
- **Default**: 2
- **Description**: Maximum number of retries for network errors (ConnectionError, TimeoutError, OSError).

---

### 2.2.8 DELAY_REQ_TIME
- **Type**: Optional[int]
- **Default**: 3
- **Description**: Delay in seconds before retrying a failed request due to network errors (ConnectionError, TimeoutError, OSError).

---

## 2.3 Proxy Settings
### 2.3.1 PROXY_URL
- **Type**: Optional[str]
- **Default**: None
- **Description**: A shortcut to configure proxy settings.
Automatically expands into PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXIES is not explicitly set.

---

### 2.3.2 PROXIES
- **Type**: Optional[Dict]
- **Default**: None
- **Description**: Dictionary format for proxy configuration, e.g. {"http": PROXY_URL, "https": PROXY_URL}.
Used to apply proxy settings to requests.

---

### 2.3.3 PROXIES_LIST
- **Type**: Optional[List[str]]
- **Default**: []
- **Description**: A list of multiple proxy URLs.
If PROXIES is not set and this is provided, a random proxy from the list will be applied per request.

---

## 2.4 Component Path
### 2.4.1 SPIDERS_PATH
- **Type**: Optional[str]
- **Default**: None
- **Description**: 
    1. If not set, finds all spiders in the `spiders/` directory and `run_all_spiders()`.  
    2. If set:  
        - for `run_spider()`: expects a module path  
        - for `run_all_spiders()`: expects a directory path  

---

### 2.4.2 ComponentInfo
`SPIDER_INTERCEPTORS_PATH`, `DOWNLOAD_INTERCEPTORS_PATH`, `ITEM_PIPELINES_PATH` and `EXTENSIONS_PATH` are all internally converted to `ComponentInfo`.
- **Type**: **Optional[Union[ComponentInfo, Dict[str, int], List[str], str, None]]**
A flexible container for specifying component module paths, supporting multiple formats. Internally, the framework will normalize all input into a consistent list of module strings. This allows users to configure components in a concise and readable manner.
Supported formats:

1. str
A single module path string will be converted into a single-item list. 
```python
"extensions.CustomExtension"
# => ["extensions.CustomExtension"]
```

2. List[str]
A list of module paths. The order of components will be preserved and used directly.
```python
["pipelines.CustomPipeline2", "pipelines.CustomPipeline1"]
```

3. Dict[str, int] (Scrapy-style format)
A dictionary mapping module paths to priority values. The framework will sort by value (lower means higher priority), and convert it into an ordered list.

The priority number follows the same convention as Scrapy: the **lower** the number, the **closer** the component is to the engine (i.e., executed later on responses and earlier on requests). Higher numbers are farther away, closer to the outer layers like the downloader or output pipeline.
```python
{
    "interceptors.CustomDownloadInterceptor1": 300,  
    "interceptors.CustomDownloadInterceptor2": 200  
}  
# => ["interceptors.CustomDownloadInterceptor2", "interceptors.CustomDownloadInterceptor1"]
```

4. None
If not specified, only the framework's built-in components will be loaded.  

> This design improves usability and flexibility, allowing components to be declared in various intuitive formats.

---

## 2.5 Scheduler Config
### 2.5.1 SCHEDULER
- **Type**: Optional[str]
- **Default**: None
- **Description**: Module path for the scheduler. Supports custom scheduler implementation.

---

### 2.5.2 DUPEFILTER
- **Type**: Optional[str]
- **Default**: None
- **Description**: Module path for the dupefilter. Supports custom dupefilter implementation.

---

### 2.5.3 BLOOM_INFO
This configuration is used to define parameters for the `DUPEFILTER` when using a Bloom filter for deduplication.

#### 2.5.3.1 MODE
- **Type**: Optional[bool]
- **Default**: False
- **Description**: Enable or disable Bloom filter deduplication. This setting has **no effect on the framework internally**, but may be used when defining a custom `DUPEFILTER`.

---

#### 2.5.3.2 SIZE
- **Type**: Optional[int]
- **Default**: 100000000
- **Description**: The number of **bits** in the Bloom filter's bitmap.

---

#### 2.5.3.3 EXPECTED
- **Type**: Optional[int]
- **Default**: 100000000
- **Description**: The expected number of elements to be inserted into the Bloom filter. Used to calculate hash functions and false positive rate.

---

#### 2.5.3.4 HASH_COUNT
- **Type**: Optional[int]
- **Default**: 0
- **Description**: Number of hash functions to use. If `0`, the framework automatically calculates an appropriate value based on `SIZE` and `EXPECTED`.

---

### 2.5.4 SCHEDULER_PERSIST
- **Type**: Optional[bool]
- **Default**: False
- **Description**: Whether to persist scheduler state. If False, Redis data will be cleared automatically when the program ends. 

**Notes**:
In **cluster mode**, due to the nature of **jump hash operations** across nodes, clearing Redis data cannot be perfectly precise even if `SCHEDULER_PERSIST` is `False`.
To mitigate this, you can use `DEDUP_TTL` to enable **TTL-based automatic expiration** in Redis.

---

### 2.5.5 DEDUP_TTL
- **Type**: Optional[int]
- **Default**: 0
- **Description**: In cluster mode, `SCHEDULER_PERSIST` cannot guarantee precise cleanup of all keys. Setting `DEDUP_TTL` enables **automatic expiration** for Redis keys associated with deduplication. 

**Note**: 
This TTL applies **only to deduplication keys**; it does **not** affect request object keys.

---

### 2.5.6 INCLUDE_HEADERS
- **Type**: Optional[List[str]]
- **Default**: []
- **Description**: A list of header field names whose values will be included in the deduplication fingerprint. This affects how requests are considered unique, without modifying the actual request headers.

---

### 2.5.7 FILTER_KEY
- **Type**: Optional[str]
- **Default**: "cffiFilter"
- **Description**: Base key used to generate internal deduplication keys: _NEW_SEEN and _SENT_SEEN.

---

### 2.5.8 DONT_FILTER
- **Type**: Optional[bool]
- **Default**: False
- **Description**: Deduplication flag.
    - When set in **global settings**, it defines the default behavior for all requests.
    - However, an option set on an **individual request** takes higher priority and will override the global configuration.

---

### 2.5.9 _NEW_SEEN
- **Type**: str
- **Default**: PrivateAttr()
- **Description**: Internal key generated from FILTER_KEY to check if a request has been newly seen. Not user-configurable.

---

### 2.5.10 _SENT_SEEN
- **Type**: str
- **Default**: PrivateAttr()
- **Description**: Internal key generated from FILTER_KEY to check if a request has already been processed. Not user-configurable.

---

## 2.6 End Behavior
### 2.6.1 WS_END_TAG
- **Type**: Optional[str]
- **Default**: "websocket end"
- **Description**: You can customize the TAG to avoid conflicts with the response content。

---

### 2.6.2 RET_COOKIES
- **Type**: Optional[Union[str, Literal[False]]]
- **Default**: "ret_cookies"
- **Description**: Specifies the field name under which response cookies will be included in the returned item. 
    - If set to a **string**, the downloader will attach the final cookies (after redirection and middleware processing) under this key. 
    - If set to `False`, cookies will not be returned in the item.

**Background and Current Status**:
Initially, this option was designed to **return cookies uniformly at the end of a request**. However, in practice:
- Some requests may require access to **specific cookies during intermediate stages**.
- The framework now supports **active retrieval on the spider/pipeline side via**:
```python
self.hooks.session.get_session_cookies(session_id)
```

This returns a `cookies_dict`, allowing developers to **manually control how and where cookies are applied** at different processing stages.

**Deprecation Notice (v0.2.x series)**:
- With the introduction of `CloseSignal` to control `session_end`, the `RET_COOKIES` option is **deprecated** and has no practical effect.
- It is retained only for **migration and reference purposes** and will be **removed in future frozen v0.2.x releases**.

---

## 2.7 Extra Config
### 2.7.1 JS_PATH
- **Type**: Optional[Union[str, bool]]
- **Default**: None
- **Description**: Path to the JavaScript directory used by the engine. Can be an absolute or relative path. If not set, defaults to a `js_path` folder located in the same directory as the script being run. If set to `False`, JS support will be disabled.

---

## 2.8 LOG_INFO
Used to configure log information, with the following configuration.

#### 2.8.1 LOG_ENABLED
- **Type**: Optional[bool]
- **Default**: True
- **Description**: Whether to enable logging. If set to False, all logging is disabled via logging.disable(logging.CRITICAL).

---

#### 2.8.2  LOG_WITH_STREAM
- **Type**: Optional[bool]
- **Default**: True
- **Description**: Whether to enable stream logging (i.e., output to terminal via sys.stdout).
This applies to both single-process and multi-process loggers.
If False, only file logging will be used (if configured).
> Note: It is recommended to use the logging system instead of `print()` for output.  
> Logging supports level-based filtering, structured formatting, and multiple output streams, while `print()` is always unfiltered.

---

#### 2.8.3 LOG_LEVEL
- **Type**: Optional[str]
- **Default**: "DEBUG"
- **Description**: Logging level, such as "DEBUG", "INFO", "WARNING", "ERROR", or "CRITICAL". This value determines the minimum severity level that will be logged.

---

#### 2.8.4 LOG_FORMAT
- **Type**: Optional[str]
- **Default**: "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
- **Description**: Format string for log messages. Used by the log formatter to format output to both console and file.

---

#### 2.8.5 LOG_DATEFORMAT
- **Type**: Optional[str]
- **Default**: "%Y-%m-%d %H:%M:%S"
- **Description**: Date and time format for log messages. Passed as datefmt to the formatter.

---

#### 2.8.6 LOG_FILE
- **Type**: Optional[str]
- **Default**: ""
- **Description**: 
    Path to the log file. If provided, logs will also be written to a file in addition to the console.
        - **Relative paths** are resolved against the location of the script where the logger is initialized.
        - **Absolute paths** are used as-is.
    The log file is rotated daily and retains 15 days by default.

---

#### 2.8.7 LOG_ENCODING
- **Type**: Optional[str]
- **Default**: "utf-8"
- **Description**: Encoding used when writing log files.

---

#### 2.8.8 LOG_SHORT_NAMES
- **Type**: Optional[bool]
- **Default**: False
- **Description**: Whether to use shortened module names in log output. If True, a custom formatter will strip long module names for brevity.

---

#### 2.8.9 LOG_FORMATTER
- **Type**: Optional[str]
- **Default**: ""
- **Description**: Dotted path to a custom formatter class, which will be dynamically imported and used.
If set, this takes precedence over LOG_SHORT_NAMES and default formatting behavior.

---

## 2.9 Databases
### 2.9.1 BaseDBInfo
Basic configuration items for all databases.

#### 2.9.1.1 URL
- **Type**: Optional[str]
- **Default**: None
- **Description**: The primary configuration field. When set, the framework will automatically maintain a connection to the database.

---

#### 2.9.1.2 HOST
- **Type**: Optional[str]
- **Default**: None
- **Description**: Combined with PORT, DB, USERNAME, and PASSWORD to generate the URL.

---

#### 2.9.1.3 PORT
- **Type**: Optional[Union[str, int]]
- **Default**: None
- **Description**: Combined with HOST, DB, USERNAME, and PASSWORD to generate the URL.

---

#### 2.9.1.4 DB
- **Type**: Optional[Union[str, int]]
- **Default**: None
- **Description**: Combined with HOST, PORT, USERNAME, and PASSWORD to generate the URL.

---

#### 2.9.1.5 USERNAME
- **Type**: Optional[str]
- **Default**: None
- **Description**: Combined with HOST, PORT, DB, and PASSWORD to generate the URL.

---

#### 2.9.1.6 PASSWORD
- **Type**: Optional[str]
- **Default**: None
- **Description**: Combined with HOST, PORT, DB, and USERNAME to generate the URL.

---

> If you prefer detailed configuration instead of directly specifying URL, at minimum you need to configure HOST and PORT. Optionally, you can also provide USERNAME and PASSWORD for authenticated connections. The framework will then automatically assemble the complete URL.

---

### 2.9.2 RedisInfo
#### 2.9.2.1 MODE
- **Type**: RedisMode
- **Default**: RedisMode.SINGLE
- **Description**: Configures the deployment mode of Redis for your project.
    - `SINGLE`: A single Redis instance. Simplest mode for most use cases.
    - `SENTINEL`: High-availability mode with automatic failover between master and slave nodes.
    - `CLUSTER`: Distributed Redis cluster for sharding data across multiple nodes.

**Notes**: 
This setting determines how other fields (`SENTINELS`, `MASTER_NAME`, `CLUSTER_NODES`) are interpreted.

---

#### 2.9.2.2 SENTINELS
- **Type**: Optional[List[tuple[str, int]]]
- **Default**: []
- **Description**: Required when MODE is SENTINEL. Configure all master and slave node addresses in the cluster.
- **Format Example**:
```python
[("127.0.0.1", 26379), ("127.0.0.2", 26379)]
```
- **Behavior**: The framework will automatically detect the master node and manage failover.

---

#### 2.9.2.3 MASTER_NAME
- **Type**: Optional[str]
- **Default**: None
- **Description**: Required for Sentinel mode. Specifies the name of the master node that clients should connect to.
- **Behavior**: Used internally to resolve the current active master when performing read/write operations.

---

#### 2.9.2.4 CLUSTER_NODES
- **Type**: Optional[List[dict]]
- **Default**: []
- **Description**: Required when `MODE` is `CLUSTER`. Configures all startup nodes for the Redis cluster.
- **Format Example**: 
```python
[
    {"host": "127.0.0.1", "port": 7000},
    {"host": "127.0.0.2", "port": 7001}
]
```
- **Behavior**: The framework uses these nodes to initialize the cluster client and automatically discovers other nodes.

---

### 2.9.3 MysqlInfo
#### 2.9.3.1 DRIVER
- **Type**: str
- **Default**: "mysql+asyncmy"
- **Description**: The default driver prefix for integration with the `SQLAlchemyMySQLManager` provided by `scrapy_cffi` (requires `pip install sqlalchemy[asyncio] aiomysql`). If you are using a custom MySQL manager, you may override this field to adapt the driver.

---

### 2.9.4 MongodbInfo
> All configuration fields are the same as in **BaseDBInfo**.

---

## 2.10 Message Queue
### 2.10.1 BaseMQInfo
#### 2.10.1.1 DRIVER
- **Type**: Optional[str]
- **Default**: "amqp"
- **Description**: The protocol scheme used by the message queue. Defaults to AMQP (`amqp://`). Can be overridden when using a custom driver.

---

#### 2.10.1.2 URL
- **Type**: Optional[str]
- **Default**: None
- **Description**: The primary configuration field. When provided, the framework will connect directly using this URL and manage reconnection automatically.

---

#### 2.10.1.3 HOST
- **Type**: Optional[str]
- **Default**: None
- **Description**: Combined with PORT, DB, USERNAME, and PASSWORD to generate the URL.

---

#### 2.10.1.4 PORT
- **Type**: Optional[Union[str, int]]
- **Default**: None
- **Description**: Combined with HOST, DB, USERNAME, and PASSWORD to generate the URL.

---

#### 2.10.1.5 USERNAME
- **Type**: Optional[str]
- **Default**: None
- **Description**: Combined with HOST, PORT, DB, and PASSWORD to generate the URL.

---

#### 2.10.1.6 PASSWORD
- **Type**: Optional[str]
- **Default**: None
- **Description**: Combined with HOST, PORT, DB, and USERNAME to generate the URL.

---

#### 2.10.1.7 MODE
- **Type**: MQMode
- **Default**: MQMode.SINGLE
- **Description**: Defines the deployment mode:
    - `SINGLE`: Single-node MQ instance.
    - `CLUSTER`: Multiple nodes, typically in a clustered MQ deployment.

---

#### 2.10.1.8 CLUSTER_NODES
- **Type**: Optional[List[str]]
- **Default**: []
- **Description**: Required when `MQMode.CLUSTER` is used.
Provides the list of all cluster node URLs, e.g.:
```python
["amqp://user:pass@host1:5672/vhost", "amqp://user:pass@host2:5672/vhost", ...]
```


---

> If you prefer detailed configuration instead of directly specifying URL, at minimum you need to configure HOST and PORT. Optionally, you can also provide USERNAME and PASSWORD for authenticated connections. The framework will then automatically assemble the complete URL.

---

### 2.10.2 RABBITMQ_INFO
#### 2.10.2.1 VHOST
- **Type**: Optional[str]
- **Default**: "/"
- **Description**: The RabbitMQ virtual host to connect to.

---

#### 2.10.2.2 EXCHANGE_NAME
- **Type**: Optional[str]
- **Default**: "scrapy_cffi"
- **Description**: The name of the exchange used for publishing and consuming messages.

---

#### 2.10.2.3 EXCHANGE_TYPE
- **Type**: Optional[str]
- **Default**: "direct"
- **Description**: The type of exchange. Supported values correspond to `aio_pika.ExchangeType`:
    - `direct`
    - `fanout`
    - `topic`
    - `headers`

---

#### 2.10.2.4 PREFETCH_COUNT
- **Type**: Optional[int]
- **Default**: 10
- **Description**: The maximum number of unacknowledged messages that a consumer can fetch in advance (QoS limit).

---

#### 2.10.2.5 DONT_FILTER
- **Type**: Optional[bool]
- **Default**: False
- **Description**: Whether to disable duplicate filtering. This option applies only to `RabbitMqScheduler`.
(Unlike `RedisScheduler`, which requires a full `RedisInfo` configuration, this setting is exclusive to RabbitMQ.)

---

### 2.10.3 KAFKA_INFO
#### 2.10.3.1 CONSUMER_GROUP
- **Type**: Optional[str]
- **Default**: "scrapy_cffi"
- **Description**: The Kafka consumer group ID. Consumers in the same group share the workload for subscribed topics.

---

#### 2.10.3.2 PERSISTENT_TIME
- **Type**: Optional[str]
- **Default**: 7*24*60*60*1000 (7 days in milliseconds)
- **Description**: The message retention time in Kafka topics. After this period, old messages are subject to deletion according to Kafka’s cleanup policy.

---

## 2.11 CPY_EXTENSIONS
Provides C extensions for performance-critical features.
## 2.11.1 DIR
- **Type**: Path
- **Default**: Path("cpy_resources")
- **Description**: Root directory where all compiled C extensions are stored.

---

## 2.11.2 RESOURCES
- **Type**: List[CPYExtension]
- **Default**: []
- **Description**: A list of C extension definitions.
Each extension is defined using the `CPYExtension` configuration.
For details and usage examples, see the dedicated documentation in **"12-cpython.md"**.