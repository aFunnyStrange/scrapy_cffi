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

---





# 2.SettingsInfo
## 2.1 General Settings
### 2.1.1 MAX_GLOBAL_CONCURRENT_TASKS
- **Type**: Optional[Union[int, None]]
- **Default**: 300
- **Description**: Defines the maximum number of concurrent asynchronous tasks allowed globally **within a single crawler engine instance**. When set to an integer, a global `BoundedSemaphore` is enabled to throttle overall task concurrency—including HTTP requests, WebSocket listeners, scheduler operations, and pipeline processing. When set to `None`, **no global concurrency restriction is enforced**, allowing the engine to freely schedule all tasks.

**Design Rationale**
Each running spider in this framework is managed by its own dedicated engine instance. Within each engine, task scheduling is fully asynchronous: requests from the scheduler, middleware processing, downloading, and spider callbacks are all submitted as non-blocking asyncio tasks. This design maximizes performance and responsiveness.

However, on certain platforms—especially Windows—the underlying `asyncio` event loop has a limited capacity for open file descriptors and concurrent coroutines. Without global throttling, mass task creation may result in errors such as:

```python
ValueError: too many file descriptors in select()
```

To mitigate such issues, this setting introduces a **global concurrency lock**. The lock is shared across all internal components and is applied at all key task creation points using `async with global_lock():`, ensuring that only a limited number of tasks are active at any moment.

This mechanism is especially critical for platform compatibility and stability, but it does **not replace** component-level concurrency controls. For example, the downloader may still enforce its own `MAX_CONCURRENT_REQ` limit to control HTTP pressure, while pipelines or Redis consumers can have their own batching logic. The global lock sits above all these, acting as the first layer of defense against resource exhaustion.

For Linux/macOS platforms, where high-performance event loops like `uvloop` are typically used and `select()` limits are much higher or nonexistent, you can safely set this value to `None` to achieve maximum throughput.


--- 

### 2.1.2 PROJECT_NAME
- **Type**: Optional[Union[str]]
- **Default**: ""
- **Description**: The queue of requested objects shared by all spiders does not need to be configured in most cases. If configuration is required, all requested objects will share this queue in `run_all_stpiders` mode. Attention should be paid to the competition issue among multiple spiders in the same scheduler.

---

### 2.1.3 ROBOTSTXT_OBEY
- **Type**: Optional[bool]
- **Default**: True
- **Description**: Whether to respect the website’s robots.txt rules.
If set to True, the crawler will skip URLs disallowed by robots.txt.

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

### 2.4.2 SPIDER_INTERCEPTORS_PATH
### 2.4.3 DOWNLOAD_INTERCEPTORS_PATH
### 2.4.4 ITEM_PIPELINES_PATH
### 2.4.5 EXTENSIONS_PATH
- **Type**: Optional[Union[ComponentInfo, Dict[str, int], List[str], str, None]]
- **Default**: ComponentInfo()
- **Description**: See "ComponentInfo" section.

---

## 2.5 Scheduler Config
### 2.5.1 SCHEDULER
- **Type**: Optional[str]
- **Default**: None
- **Description**: Module path for the scheduler. Supports custom scheduler implementation.

---

### 2.5.2 SCHEDULER_PERSIST
- **Type**: Optional[bool]
- **Default**: False
- **Description**: Whether to persist scheduler state. If False, Redis data will be cleared automatically when the program ends.

---

### 2.5.3 INCLUDE_HEADERS
- **Type**: Optional[List]
- **Default**: []
- **Description**: A list of header field names whose values will be included in the deduplication fingerprint. This affects how requests are considered unique, without modifying the actual request headers.

---

### 2.5.4 FILTER_KEY
- **Type**: Optional[str]
- **Default**: "cffiFilter"
- **Description**: Base key used to generate internal deduplication keys: _FILTER_NEW_SEEN_REQ_KEY and _FILTER_IS_REQ_KEY.

---

### 2.5.5 DONT_FILTER
- **Type**: Optional[bool]
- **Default**: False
- **Description**: Deduplication flag.
    - When set in **global settings**, it defines the default behavior for all requests.
    - However, an option set on an **individual request** takes higher priority and will override the global configuration.

---

### 2.5.6 _FILTER_NEW_SEEN_REQ_KEY
- **Type**: str
- **Default**: PrivateAttr()
- **Description**: Internal key generated from FILTER_KEY to check if a request has been newly seen. Not user-configurable.

---

### 2.5.7 _FILTER_IS_REQ_KEY
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
- **Description**: Specifies the field name under which response cookies will be included in the returned item. If set to a string, the downloader will attach the final cookies (after redirection and middleware processing) under this key. If set to `False`, cookies will not be returned in the item.

---

## 2.7 Extra Config
### 2.7.1 JS_PATH
- **Type**: Optional[Union[str, bool]]
- **Default**: None
- **Description**: Path to the JavaScript directory used by the engine. Can be an absolute or relative path. If not set, defaults to a `js_path` folder located in the same directory as the script being run. If set to `False`, JS support will be disabled.

---

### 2.7.2 REDIS_INFO
- **Type**: Optional[RedisInfo]
- **Default**: RedisInfo()
- **Description**: See "RedisInfo" section.

---

### 2.7.3 MYSQL_INFO
- **Type**: Optional[MysqlInfo]
- **Default**: MysqlInfo()
- **Description**: See "MysqlInfo" section.

---

### 2.7.4 MONBODB_INFO
- **Type**: Optional[MongodbInfo]
- **Default**: MongodbInfo()
- **Description**: See "MongodbInfo" section.

---

### 2.7.5 LOG_INFO
- **Type**: Optional[LogInfo]
- **Default**: LogInfo()
- **Description**: See "LogInfo" section.

---





# 3.ComponentInfo
- **Type**: **Optional[Union[ComponentInfo, Dict[str, int], List[str], str, None]]**
A flexible container for specifying component module paths, supporting multiple formats. Internally, the framework will normalize all input into a consistent list of module strings. This allows users to configure components in a concise and readable manner.
Supported formats:

## 3.1 str
A single module path string will be converted into a single-item list. 
```python
"extensions.CustomExtension"
# => ["extensions.CustomExtension"]
```

## 3.2 List[str]
A list of module paths. The order of components will be preserved and used directly.
```python
["pipelines.CustomPipeline2", "pipelines.CustomPipeline1"]
```
## 3.3 Dict[str, int] (Scrapy-style format)
A dictionary mapping module paths to priority values. The framework will sort by value (lower means higher priority), and convert it into an ordered list.

The priority number follows the same convention as Scrapy: the **lower** the number, the **closer** the component is to the engine (i.e., executed later on responses and earlier on requests). Higher numbers are farther away, closer to the outer layers like the downloader or output pipeline.
```python
{
    "interceptors.CustomDownloadInterceptor1": 300,  
    "interceptors.CustomDownloadInterceptor2": 200  
}  
# => ["interceptors.CustomDownloadInterceptor2", "interceptors.CustomDownloadInterceptor1"]
```

## 3.4 None
If not specified, only the framework's built-in components will be loaded.  

> This design improves usability and flexibility, allowing components to be declared in various intuitive formats.

---





# 4.LogInfo
## 4.1 LOG_ENABLED
- **Type**: Optional[bool]
- **Default**: True
- **Description**: Whether to enable logging. If set to False, all logging is disabled via logging.disable(logging.CRITICAL).

---

## 4.2  LOG_WITH_STREAM
- **Type**: Optional[bool]
- **Default**: True
- **Description**: Whether to enable stream logging (i.e., output to terminal via sys.stdout).
This applies to both single-process and multi-process loggers.
If False, only file logging will be used (if configured).
> Note: It is recommended to use the logging system instead of `print()` for output.  
> Logging supports level-based filtering, structured formatting, and multiple output streams, while `print()` is always unfiltered.

---

## 4.3 LOG_LEVEL
- **Type**: Optional[str]
- **Default**: "DEBUG"
- **Description**: Logging level, such as "DEBUG", "INFO", "WARNING", "ERROR", or "CRITICAL". This value determines the minimum severity level that will be logged.

---

## 4.4 LOG_FORMAT
- **Type**: Optional[str]
- **Default**: "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
- **Description**: Format string for log messages. Used by the log formatter to format output to both console and file.

---

## 4.5 LOG_DATEFORMAT
- **Type**: Optional[str]
- **Default**: "%Y-%m-%d %H:%M:%S"
- **Description**: Date and time format for log messages. Passed as datefmt to the formatter.

---

## 4.6 LOG_FILE
- **Type**: Optional[str]
- **Default**: ""
- **Description**: 
    Path to the log file. If provided, logs will also be written to a file in addition to the console.
        - **Relative paths** are resolved against the location of the script where the logger is initialized.
        - **Absolute paths** are used as-is.
    The log file is rotated daily and retains 15 days by default.

---

## 4.7 LOG_ENCODING
- **Type**: Optional[str]
- **Default**: "utf-8"
- **Description**: Encoding used when writing log files.

---

## 4.8 LOG_SHORT_NAMES
- **Type**: Optional[bool]
- **Default**: False
- **Description**: Whether to use shortened module names in log output. If True, a custom formatter will strip long module names for brevity.

---

## 4.9 LOG_FORMATTER
- **Type**: Optional[str]
- **Default**: ""
- **Description**: Dotted path to a custom formatter class, which will be dynamically imported and used.
If set, this takes precedence over LOG_SHORT_NAMES and default formatting behavior.

---





# 5.RedisInfo
## 5.1 URL
- **Type**: Optional[str]
- **Default**: None
- **Description**: The primary configuration field. When set, the framework will automatically maintain a connection to the Redis database.

---

## 5.2 HOST
- **Type**: Optional[str]
- **Default**: None
- **Description**: Combined with PORT, DB, USERNAME, and PASSWORD to generate the REDIS_URL.

---

## 5.3 PORT
- **Type**: Optional[Union[str, int]]
- **Default**: None
- **Description**: Combined with HOST, DB, USERNAME, and PASSWORD to generate the REDIS_URL.

---

## 5.4 DB
- **Type**: Optional[Union[str, int]]
- **Default**: None
- **Description**: Combined with HOST, PORT, USERNAME, and PASSWORD to generate the REDIS_URL.

---

## 5.5 USERNAME
- **Type**: Optional[str]
- **Default**: None
- **Description**: Combined with HOST, PORT, DB, and PASSWORD to generate the REDIS_URL.

---

## 5.6 PASSWORD
- **Type**: Optional[str]
- **Default**: None
- **Description**: Combined with HOST, PORT, DB, and USERNAME to generate the REDIS_URL.

---
> If you prefer detailed configuration instead of directly specifying REDIS_URL, at minimum you need to configure HOST and PORT. Optionally, you can also provide USERNAME and PASSWORD for authenticated Redis connections. The framework will then automatically assemble the complete REDIS_URL.

# 6.MysqlInfo
## 6.1 DRIVER
- **Type**: str
- **Default**: "mysql+asyncmy"
- **Description**: The default driver prefix for integration with the `SQLAlchemyMySQLManager` provided by `scrapy_cffi` (requires `pip install sqlalchemy[asyncio] aiomysql`). If you are using a custom MySQL manager, you may override this field to adapt the driver.

> All other configuration fields are the same as in **RedisInfo**.

# 7.MongodbInfo
> All configuration fields are the same as in **RedisInfo**.