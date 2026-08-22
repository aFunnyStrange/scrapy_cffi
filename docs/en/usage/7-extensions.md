# 1.Introduction
`scrapy_cffi` provides a set of signal mechanisms that allow users to register extensions and implement custom behaviors outside the framework core. The signal system works like a broadcast mechanism and encapsulates all signal data using a unified `SignalInfo` object.

Even when no extensions are enabled, the framework will still emit signals internally. However, these signals will be immediately discarded. Only when extensions are registered and activated will the signal system take effect.

**Note:**
- 1.Since `scrapy_cffi` is based on a **fully asynchronous scheduling model**, signal delivery may not be immediate. Therefore, signals are intended for **extension and observation**, not for strict timing or control logic. If you require precise event timing, `scrapy_cffi` may not be suitable. However, each `SignalInfo` instance includes a `signal_time` timestamp, which can be used for downstream processing or analysis.
- 2.When using `RedisSpider`, due to its **persistent listening behavior**, the spider process only exits when manually interrupted (e.g., via Ctrl+C). In such cases, it is possible that some signals remain unprocessed before the crawler's shutdown logic is triggered. These signals may be dropped, but this is considered an **acceptable trade-off** as long as the process exits cleanly.


---


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


---


# 3.Registering Extensions
To use custom signal handlers, follow these steps:
1.Inherit the `Extension` class
```python 
from scrapy_cffi.extensions import signals, Extension
```

2.Register signals in the `from_crawler` method
```python 
hooks.signals.connect(signals.engine_started, your_callback_function)
```

3.Define your signal callback function
To see a working example, you can explore the built-in demo:
```python
scrapy_cffi demo
```

# 4. Built-in opt-in extensions

Generated projects do not enable any Extension by default. Signals with no
listeners are discarded, so ordinary crawlers do not pay for monitoring or
SMTP I/O.

`CrawlerMonitorExtension` publishes lifecycle and error events to the optional
monitoring Hub. High-frequency request, response, drop, and item signals are
counted locally and published only after `MONITOR_INFO.EVENT_BATCH_SIZE`
observations. Once enabled, it owns one low-frequency heartbeat task from the
first Engine start through explicit shutdown. Heartbeats affect Hub
availability only and never control crawler completion.

```python
from scrapy_cffi.extensions import CrawlerMonitorExtension

settings.MONITOR_INFO.HUB_URL = "http://127.0.0.1:6800"
settings.MONITOR_INFO.HEARTBEAT_INTERVAL = 15.0
settings.EXTENSIONS_PATH = CrawlerMonitorExtension
```

`EmailNotificationExtension` uses lazy SMTP connections and
`asyncio.to_thread()`. By default it sends an aggregated engine-stop summary;
immediate error messages require `EMAIL_INFO.SEND_ON_ERROR = True`.

```python
from scrapy_cffi.extensions import EmailNotificationExtension

settings.EMAIL_INFO.HOST = "smtp.example.com"
settings.EMAIL_INFO.USERNAME = "crawler@example.com"
settings.EMAIL_INFO.TO_ADDRESSES = ["ops@example.com"]
settings.EXTENSIONS_PATH = EmailNotificationExtension
```

Keep `EMAIL_INFO__PASSWORD` in the ignored project `.env`. See
[the monitoring console](17-monitoring.md) for server and Hub modes.
