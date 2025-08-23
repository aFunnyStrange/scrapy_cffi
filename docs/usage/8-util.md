# 1.Introduction
`scrapy_cffi.utils` provides a set of commonly used utility functions covering multiple areas, mainly focusing on **Concurrency**, **Logging**, and **Media** processing.

# 2.Concurrency
## 2.1 run_coroutine_in_new_loop
Run a coroutine inside a **new event loop** in an asynchronous environment.
> It runs in its own thread pool, making it safe to execute coroutines within an existing async context.

```python 
import asyncio
from scrapy_cffi.utils import run_coroutine_in_new_loop

async def coro(x):
    await asyncio.sleep(1)
    return x * 2

result = await run_coroutine_in_new_loop(coro, 10)
print(result)  # output: 20
```

Notes:
- `target` can be a coroutine object or a function returning a coroutine
- Supports `*args, **kwargs`
- Returns the result of the coroutine execution

## 2.2 run_coroutine_in_thread
Run a coroutine inside a **new thread** in an asynchronous environment.
Similar to `run_coroutine_in_new_loop`, but uses thread isolation instead of a new loop.
Useful for concurrent execution without blocking the main event loop.

**Example:**
```python
future = run_coroutine_in_thread(coro, 10)
result = await future
print(result)  # output: 20
```

## 2.3 ProcessTaskManager
Run asynchronous functions inside **synchronous process environments**, supporting both result-returning and background execution.
**Main methods:**
- `await manager.run(func, return_result=True, **kwargs)`
    - Run a task and return the result
- `manager.terminate_all()`
    - Terminate all spawned child processes

**Features:**
- Automatically registers `atexit` cleanup
- Cross-process signal handling support on Linux/macOS
- On Windows, Ctrl+C may cause hangs (use with caution)

## 2.4 ProcessManager
Implements a native Python **multiprocessing RPC** model: server registers, client calls.
Usage examples: https://github.com/aFunnyStrange/scrapy_cffi/blob/main/tests/_processManager
> ProcessManager can register functions, classes, or object instances for client calls, but cannot directly register constants or primitive types. To share constants, wrap them inside a function.
> Communication is done over TCP sockets — by default it runs on localhost, but if you bind to `0.0.0.0` or a public IP, clients can connect from LAN or even the internet (use caution with security).

**Summary:**
- start_server(run_mode=1)：background mode, launches a server inside the main process
- start_server(run_mode=0)：blocking mode, run as standalone process
- start_client()：start client
- shutdown()：shutdown server

Comparison Table:
| Technology | Use Case | Pros | Cons |
| --------- | ----------- | ----------- | ----------- |
| **ProcessManager** | Local/small multiprocess | Simple, direct, registerable | Not scalable, high overhead |
| **ProcessTaskManager** | Async + process isolation | Lightweight, easy to use | Single-machine only |
| **MQ/Redis/Kafka** | Distributed task queues | Scalable, cross-language | Complex setup, learning curve |

> Combination of **ProcessManager + ProcessTaskManager**: Best for small to mid-sized projects, fast development, single-machine or LAN.
> **MQ/Redis**: For large-scale distributed systems, heavy workloads, or frequent cross-machine calls.


# 3.Log
## 3.1 init_logger
Initialize a **single-process logger**. Recommended to pass `__name__` as `logger_name` to avoid using the default root logger.

**Features:**: 
- Configure log level, format, date format from `LogInfo`
- Support console and file output
- Support custom formatters and short names

**Example:**
```python 
from scrapy_cffi.models.api import LogInfo
from scrapy_cffi.utils import init_logger

log_info = LogInfo(
    LOG_ENABLED=True,
    LOG_LEVEL="DEBUG",
    LOG_FILE="logs/app.log",
    LOG_SHORT_NAMES=True
)

logger = init_logger(log_info, __name__)
logger.info("Logger initialized successfully")
```

**Notes:**
- Set `log_info.LOG_ENABLED=False` to disable logging
- Support custom formatters via `LOG_FORMATTER`
- File logging auto-creates directories, daily rotation (15-day backup)


## 3.2 start_multiprocess_log_listener
Create a **multiprocess log listener** to collect logs from different processes into a unified output.

**Features:**: 
- Console + file output
- Collects logs via `multiprocessing.Queue`
- Managed by `QueueListener`
    
**Example:**
```python
log_queue, listener = start_multiprocess_log_listener(log_info, with_stream=True)
# log_queue can be passed to child processes with QueueHandler
# listener automatically collects logs and outputs them
```

**Notes:**
- `with_stream=True`: enable terminal output
- `log_file` auto-creates directory if set
- Returns `(log_queue, listener)`, with `listener` already started

## 3.3 init_logger_multiprocessing
Initialize a **multiprocess logger**, suitable for child processes with queue-based logging.

**Features:**: 
- Similar to single-process logger, but with `QueueHandler` support
- Allows extra handlers via `extra_handlers`

**Example:**
```python
from scrapy_cffi.utils import init_logger_multiprocessing

logger = init_logger_multiprocessing(
    logger_name="worker",
    log_level="INFO",
    log_queue=log_queue,
    with_stream=True
)
logger.info("Child process logger ready")
```

**Notes:**
- `log_queue` can forward logs to the main process
- `formatter` supports custom formats
- `extra_handlers` for custom log processing

# 4.Media
Import from `scrapy_cffi.utils.media`
## 4.1 guess_content_type(byte_data: bytes) -> str
Detect MIME type from byte content.
- Requires `python-magic` (Unix) or `python-magic-bin` (Windows)

**Example:**
```python
mime_type = guess_content_type(file_bytes)
print(mime_type)  # e.g. "image/png" 或 "video/mp4"
```

## 4.2 get_image_info_from_bytes(image_bytes: bytes) -> Union[dict, str]
Extract image metadata directly from byte stream (no temp files).

**Return Example:**
```python
{
    "format": "PNG",
    "mode": "RGB",
    "width": 800,
    "height": 600
}
```

**Example:**
```python
info = get_image_info_from_bytes(image_bytes)
if isinstance(info, dict):
    print(info["width"], info["height"])
else:
    print("Failed:", info)
```

## 4.3 get_video_info_from_bytes(image_bytes: bytes) -> Union[dict, str]
Extract video metadata directly from byte stream (no temp files).
- Requires system-installed `ffprobe` (FFmpeg)

**Return Example:**
```python
{
    "width": 1920,
    "height": 1080,
    "duration": 12.5
}
```

**Example:**
```python
info = get_video_info_from_bytes(video_bytes)
if isinstance(info, dict):
    print(info["duration"])
else:
    print("Failed:", info)
```

## 4.4 get_image_info_from_tempfile(image_bytes: bytes) -> dict
Extract image metadata via **temporary file**.
Stable for cross-platform packaging or restricted environments.

**Example:**
```python
info = get_image_info_from_tempfile(image_bytes)
print(info["format"], info["width"], info["height"])
```

Notes:
- Creates and auto-deletes temporary file
- Returns error string if extraction fails

## 4.4 get_video_info_from_tempfile(video_bytes: bytes) -> dict
Extract video metadata via **temporary file**, using `hachoir` pure Python library.

**Return Example:**
```python
{
    "width": 1280,
    "height": 720,
    "duration": 10.0
}
```

**Example:**
```python
info = get_video_info_from_tempfile(video_bytes)
print(info["width"], info["height"], info["duration"])
```

Notes:
- More portable, suitable for standalone apps
- Auto-cleans temporary files
- Returns error string on failure