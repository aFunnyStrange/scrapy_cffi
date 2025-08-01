# 1.Introduction
`scrapy_cffi` is a fully asynchronous web crawling framework for Python. It does **not** support `scrapy`-style CLI commands such as `scrapy crawl ...`.

Because the framework is built on top of Python's `asyncio`, it follows a centralized event loop principle. This means certain exceptions (like keyboard interrupts) can only be handled at the top-level loop. To accommodate different usage scenarios, the framework provides two modes: **Standard User Mode** and **Advanced User Mode**.

# 2.Standard User Mode
In most use cases, you can simply use the synchronous interfaces run_spider_sync or run_all_spiders_sync. These are plug-and-play APIs that automatically create and run the event loop internally, allowing you to start spiders without dealing with asynchronous logic.

# 3.Advanced User Mode
If you need fine-grained control (e.g., integrating with an existing multithreaded, multiprocess, or asynchronous system), you can use the asynchronous versions `run_spider` and `run_all_spiders` directly.
When working with custom event loops (`new_loop`), be aware of potential risks related to sharing objects across loops—manual handling is required.

⚠️ **Notes:**
- The framework provides built-in **thread-level logging**. If you require **process-level logging**, ensure that multiple processes do not write to the same log file concurrently.
- The framework only provides reference implementations; advanced users must manage logging and system resources appropriately.

```python 
from scrapy_cffi.utils import start_multiprocess_log_listener, init_logger_multiprocessing
```

# 4.Additional Information
## 4.1 ❓ **Why is there no global `settings.py`?**
Unlike `Scrapy`, which typically launches one spider per process, `scrapy_cffi` allows multiple spiders to run within a single process. Defining a global configuration file (like `settings.py`) can lead to unintended side effects—such as overriding parent-level or scheduler-wide configurations—especially when spiders are used as downstream components in a centralized system.
To avoid such conflicts, `scrapy_cffi` uses explicit settings injection: configuration must be passed as arguments when launching spiders. This ensures that spiders remain isolated and do not affect the global context. Additionally, it enables easy batch construction of multiple spiders, each with its own customized settings.

🔧 **Utilities & API Helpers**
`scrapy_cffi.utils` provides a set of utility functions to simplify common tasks, especially for users transitioning from Scrapy or integrating with legacy configurations:
1.to_scrapy_settings_py(settings_obj)                       Converts a `SettingsInfo` object into a Scrapy-style `settings.py` string. (You must write it to a file manually.)
2.load_settings_from_py(filepath: str, auto_upper=True)     Loads settings from a Scrapy-style `settings.py` file.
3.convert_to_toml(py_path: str, toml_path: str)             Converts `settings.py` to `.toml` format.
4.ScrapyRunner                                              Launches a Scrapy project via subprocess using a Python script. Useful for hybrid scheduling.

## 4.2 scrapy_cffi 设计思想
The lifecycle of a single spider is consistent with Scrapy. For details, refer to `images/spider.png`.

Each spider is bound to its own **engine**, while all other components (middleware managers, downloader, signal hooks, etc.) are **shared** across spiders and coordinated by a top-level `Crawler` object, which manages the overall lifecycle. See `images/结构图.png` for a full architecture diagram.

When running `run_all_spiders`, all spiders execute within the **same thread and event loop**, allowing seamless integration with external asyncio-based systems or frameworks. This shared-loop design keeps things simple and efficient for standard use cases.

However, if isolation is needed—such as giving each spider its own environment or event loop—you can switch to a multi-threaded or multi-process mode using `run_spider`. The framework's interface is designed with this flexibility in mind: it supports multiple spiders per loop, **while also enabling users to fully control execution at a higher level**. See `images/上层调度.png` for how to build custom orchestration logic.

This design allows `scrapy_cffi` to adapt cleanly to both **monolithic** and **distributed** usage patterns.