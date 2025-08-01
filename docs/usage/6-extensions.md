# 1.Introduction
`scrapy_cffi` provides a set of signal mechanisms that allow users to register extensions and implement custom behaviors outside the framework core. The signal system works like a broadcast mechanism and encapsulates all signal data using a unified `SignalInfo` object.
Even when no extensions are enabled, the framework will still emit signals internally. However, these signals will be immediately discarded. Only when extensions are registered and activated will the signal system take effect.

**Note:**
- 1.Since `scrapy_cffi` is based on a **fully asynchronous scheduling model**, signal delivery may not be immediate. Therefore, signals are intended for **extension and observation**, not for strict timing or control logic. If you require precise event timing, `scrapy_cffi` may not be suitable. However, each `SignalInfo` instance includes a `signal_time` timestamp, which can be used for downstream processing or analysis.
- 2.When using `RedisSpider`, due to its **persistent listening behavior**, the spider process only exits when manually interrupted (e.g., via Ctrl+C). In such cases, it is possible that some signals remain unprocessed before the crawler's shutdown logic is triggered. These signals may be dropped, but this is considered an **acceptable trade-off** as long as the process exits cleanly.

# 2.SignalInfo Overview
# 2.1 Core Component Signals
```python
engine_started = object()        # Engine started
SignalInfo(signal_time=time.time())

engine_stopped = object()        # Engine stopped
SignalInfo(signal_time=time.time())

scheduler_empty = object()       # Scheduler is empty
SignalInfo(signal_time=time.time())

task_error = object()            # Task failed
SignalInfo(signal_time=time.time(), reason=result)
```

# 2.2 Spider Lifecycle Signals
```python
spider_opened = object()        # Spider opened
SingalInfo(spider: Spider, signal_time=time.time())

spider_closed = object()        # Spider closed
SingalInfo(spider: Spider, signal_time=time.time())

spider_error = object()       # Spider error
SingalInfo(response: Response, exception: BaseException, spider: Spider, signal_time=time.time())
```

# 2.3 Request Scheduling Signals
```python
request_scheduled = object()     # Request successfully scheduled
SingalInfo(signal_time=time.time(), request=request)

request_dropped = object()       # Request was dropped
SignalInfo(signal_time=time.time(), request=request, reason=reason)
```

# 2.4 Downloader Signals
```python
request_reached_downloader = object()  # Request sent to downloader
SignalInfo(signal_time=time.time(), request=request)

response_received = object()           # Response received
SignalInfo(signal_time=time.time(), request=request, response=response)
```

# 2.5 Item Pipeline Signals
```python
item_scraped = object()          # Item scraped successfully
SignalInfo(signal_time=time.time(), item=item, spider=spider)

item_dropped = object()          # Item was dropped
SignalInfo(signal_time=time.time(), item=item, reason=reason)

item_error = object()            # Exception during item processing
SignalInfo(signal_time=time.time(), item=item, exception=exception)
```
**Note:**
The signals `item_dropped` and `item_error` are **not emitted by the framework itself**. They are **reserved for user-defined extensions or middleware**. If you want to monitor item drops or handle item-related exceptions via signals, you must manually trigger them in your pipeline logic using the hooks.

# 3.Registering Extensions
To use custom signal handlers, follow these steps:
1.Inherit the `Extension` class
```python 
from scrapy_cffi.extensions import signals, Extension
```

2.Register signals in the `from_crawler` method
```python 
crawler.signalManager.connect(signals.engine_started, your_callback_function)
```

3.Define your signal callback function
To see a working example, you can explore the built-in demo:
```python
scrapy_cffi demo
```
