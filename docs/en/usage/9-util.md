# 1.Introduction
`scrapy_cffi.utils` provides utility submodules for **Concurrency**, **Logging**, **Media**, **JsonLoad**, **Protobuf**, **ScrapyRunner**, **fd** and **envConfig**.

**Import paths (recommended since 0.3.x):**

| Need | Import |
| ---- | ------ |
| Hash / ids | `from scrapy_cffi.utils.algorithm import do_sha1` |
| JSON extract | `from scrapy_cffi.utils.jsonLoad import extract_json_chain` |
| MIME sniff | `from scrapy_cffi.utils.media import guess_content_type` |
| .env ↔ settings | `from scrapy_cffi.utils.envConfig import settings_to_env` |
| FD limits | `from scrapy_cffi.utils.fd import FDUtil` |

Legacy barrel `from scrapy_cffi.utils import do_sha1` still works — symbols load **lazily** (one submodule at a time). Prefer submodule paths in tools/scripts to avoid pulling `robot` / `common` when unused.

Optional media deps: `pip install scrapy_cffi[media]` (`filetype`, `Pillow`, `hachoir`).


---


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
Usage examples: https://github.com/aFunnyStrange/scrapy_cffi/tree/main/examples/process_manager
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


---


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


---


# 4.Media
Import from `scrapy_cffi.utils.media` (requires `pip install scrapy_cffi[media]` or `pip install filetype Pillow hachoir`).

All functions operate directly on byte streams provided as input.

## 4.1 guess_content_type
**Purpose**: Detect the MIME type from raw byte content.

**Requirements**:
- `filetype` (cross-platform; replaces platform-specific `python-magic`)

**Parameters**:
- `byte_data: bytes` – raw byte content.

**Returns**:
- `str` – detected MIME type, or `application/octet-stream` when unknown. Error message string on failure.

**Example Usage**:
```python
from scrapy_cffi.utils.media import guess_content_type

mime_type = guess_content_type(file_bytes)
print(mime_type)  # e.g., "image/png" or "video/mp4"
```

## 4.2 get_image_info_from_bytes
**Purpose**: Extract image metadata directly from a byte stream (no temporary files).

**Parameters**:
- `image_bytes: bytes` – image data in bytes.

**Returns**:
- `dict` if successful, containing image info.
- `str` with error message if failed.

**Return Example**:
```python
{
    "format": "PNG",
    "mode": "RGB",
    "width": 800,
    "height": 600
}
```

**Example Usage**:
```python
info = get_image_info_from_bytes(image_bytes)
if isinstance(info, dict):
    print(info["width"], info["height"])
else:
    print("Failed:", info)
```

## 4.3 get_video_info_from_bytes
**Purpose**: Extract video metadata directly from a byte stream (no temporary files).

**Requirements**:
- System-installed `ffprobe` (part of FFmpeg).

**Parameters**:
- `video_bytes: bytes` – video data in bytes.

**Returns**:
- `dict` if successful, containing video info (`width`, `height`, `duration`).
- `str` with error message if failed.

**Return Example**:
```python
{
    "width": 1920,
    "height": 1080,
    "duration": 12.5
}
```

**Example Usage**:
```python
info = get_video_info_from_bytes(video_bytes)
if isinstance(info, dict):
    print(info["duration"])
else:
    print("Failed:", info)
```

## 4.4 get_image_info_from_tempfile
**Purpose**: Extract image metadata using a temporary file.
Useful for cross-platform packaging or restricted environments.

**Parameters**:
- `image_bytes: bytes` – image data.

**Returns**:
- `dict` if successful.
- `str` with error message if failed.

**Notes**:
- Creates and automatically deletes a temporary file.

**Example Usage**:
```python
info = get_image_info_from_tempfile(image_bytes)
print(info["format"], info["width"], info["height"])
```

## 4.5 get_video_info_from_tempfile
**Purpose**: Extract video metadata using a temporary file and the pure Python `hachoir` library.

**Parameters**:
- `video_bytes: bytes` – video data.

**Returns**:
- `dict` if successful (`width`, `height`, `duration`).
- `str` with error message if failed.

**Notes**:
- More portable; suitable for standalone applications.
- Automatically cleans up temporary files.

**Return Example**:
```python
{
    "width": 1280,
    "height": 720,
    "duration": 10.0
}
```

**Example Usage**:
```python
info = get_video_info_from_tempfile(video_bytes)
print(info["width"], info["height"], info["duration"])
```

**Dependencies & Installation**:
```text
# MIME detection (cross-platform):
pip install scrapy_cffi[media]
# or: pip install filetype

# Pillow for image processing:
pip install Pillow

# Hachoir for video metadata extraction:
pip install hachoir

# FFmpeg (ffprobe) for video byte stream parsing:
Linux: sudo apt install ffmpeg
macOS: brew install ffmpeg
Windows: Download from https://ffmpeg.org/download.html and add to PATH
```


---


# 5.JsonLoad
This module provides a powerful JSON extraction utility, serving as the underlying implementation for `response.extract_json` and `response.extract_json_strong` methods in your scraper.
The main difference is that `response` methods automatically pass `text=response.text` as input.
## 5.1 extract_nested_objects
**Purpose**: Extract JSON objects from text using regex.

**Parameters**:
- `text: str` – the text content to search.
- `key: str` (optional) – extract only values associated with this key. If not provided, all JSON blocks are returned.
- `re_rule: str` (optional) – custom regex for matching; no need to import `re` or `regex`.

**Returns**:
- Single match → returns the JSON object directly.
- Multiple matches → returns a list of JSON objects.
- If no key is provided → returns all JSON blocks.

**Note**: Cannot verify JSON validity; purely regex-based extraction.

## 5.2 JSONScanner
**Purpose**: Advanced string scanning JSON extractor built on top of `JSONExtractor`. Handles nested JSONs that may fail in lower-level parsing.

**Usage**:
```python
json_scanner = JSONScanner(strict_level=0)
results = json_scanner.scan_text(text, key="target_key")
```

**Parameters**:
- `strict_level` – strictness level for JSON parsing (default 2):
    - 2 → uses orjson (fastest, strictest)
    - 1 → uses Python built-in json
    - 0 → uses json5 (most lenient, supports comments and missing quotes)

- `text: str` – text to extract JSON from.
- `key: str` (optional) – specific key to extract.
- `re_rule: str` (optional) – custom regex for direct matching.

**Returns**:
- Single match → JSON object (`dict` or `list`).
- Multiple matches → list of JSON objects.

**Behavior**:
- Can recursively extract nested JSON within string values.
- Automatically avoids duplicate extractions.
- Handles malformed JSON (comments, missing quotes) according to `strict_level`.

**Example**:
```python
scanner = JSONScanner(strict_level=0)
data = scanner.scan_text(text, key="user")
print(data)
```

### 5.2.1 Chain Key Scanning
When a single key is too broad, use chain scanning to narrow the search layer by layer:

```python
from scrapy_cffi.utils import extract_json_chain

data = extract_json_chain(text, keys=["payload", "items", "id"])
```

This first extracts all `payload` values, converts those values back to text, scans them for `items`, then scans those results for `id`. Results are deduplicated at each layer.

## 5.3 JSONExtractor (Internal)
**Purpose**: Base class for `JSONScanner`, provides lower-level extraction methods:
- `remove_json_comments(text: str) -> str` – remove JavaScript-style comments.
- `try_parse_json_recursive(json_str: str, max_depth: int = 5)` – recursive parsing of JSON strings.
- `find_key_recursively(obj: Any, target_key: str)` – search for key recursively in dict/list.
- `find_brace_pairs_safe(text: str)` – safe extraction of top-level JSON objects by brace matching.
- `extract(text: str, key: str = "", re_rule: str = "")` – unified extraction interface used by `JSONScanner`.

**Key Notes**:
- `JSONScanner.scan_text` is effectively a robust high-level parser capable of handling:
    - Single JSON objects
    - Nested JSONs
    - Multiple concatenated JSON objects

- It automatically chooses parsing strategy based on `strict_level`.
- Deduplicates results and supports parsing of JSON stored as strings inside JSON.


---


# 6.Protobuf
`ProtobufFactory` is a utility class that provides unified methods for encoding and decoding **Protobuf** and **gRPC** messages.
All methods are **static**. The framework always includes its refactored pure-Python codec, so no extra dependency is required.

Install the optional Rust backend when higher throughput is needed:

```bash
pip install "scrapy_cffi[protobuf]"
```

If `pyblackboxprotobuf` loads successfully, scrapy_cffi binds the codec API to
that Rust implementation once during import. If the package is absent or its
native library cannot load on the current platform, the framework falls back
to `scrapy_cffi.utils.blackboxprotobuf` automatically. Existing imports and
`ProtobufFactory` calls remain unchanged. Use
`ProtobufFactory.backend_name()` to inspect the active `rust` or `python`
backend.

The same selected backend is used by `grpc_encode`, `grpc_stream_encode`, and
`grpc_decode`. scrapy_cffi owns the five-byte gRPC framing, gzip handling, and
validation rules so Rust and Python installations expose identical behavior;
the Protobuf payload inside each frame is accelerated when Rust is active.

Starting from **version ≥ 0.2.4**, `scrapy_cffi` refactored the `blackboxprotobuf` source code (version 1.4.2), keeping only two commonly used APIs:
- `encode_message`
- `decode_message`

## 6.1 protobuf_encode
**Purpose**: Encode a Python dictionary into a Protobuf byte stream.

**Implementation**: Directly calls `blackboxprotobuf.encode_message`.

**Signature**:
```python
@staticmethod
def protobuf_encode(data: Dict, typedef: Dict) -> bytes
```

## 6.1 protobuf_decode
**Purpose**: Decode a Protobuf byte stream into a Python dictionary.

**Implementation**: Directly calls `blackboxprotobuf.decode_message`.

**Signature**:
```python
@staticmethod
def protobuf_decode(data: bytes) -> Tuple[Dict, Dict]
```
- Returns a tuple `(decoded_data, typedef)`.

## 6.1 grpc_encode
**Purpose**: Encode a Python dictionary into a gRPC-compliant message.

**Behavior**:
- Uses `blackboxprotobuf.encode_message` for the payload.
- Prepends a gRPC message header:
    - 1 byte: compression flag (0 = no compression, 1 = gzip compression)
    - 4 bytes: message length (big-endian)
- Optionally compresses the message body with gzip if `is_gzip=True`.

**Signature**:
```python
@staticmethod
def grpc_encode(data: Dict, typedef: Dict, is_gzip: bool=False) -> bytes
```
- Returns the full gRPC-encoded byte sequence.

## 6.1 grpc_stream_encode
**Purpose**: Encode multiple gRPC messages into a single concatenated byte stream.

**Behavior**:
- Accepts data: `List[Tuple[Dict, Dict]]`, where each tuple contains a message and its typedef.
- Encodes each message individually using `grpc_encode`.
- Concatenates all encoded messages into a single byte stream.

**Signature**:
```python
@staticmethod
def grpc_stream_encode(data: List[Tuple[Dict, Dict]], is_gzip=False) -> bytes
```
- Returns the concatenated byte stream of all messages.

## 6.1 grpc_decode
**Purpose**: Decode gRPC messages from a byte stream.

**Behavior**:
- Automatically parses the gRPC message header (compression flag + length).
- Supports both single messages and concatenated multi-message streams.
- Automatically decompresses gzip-compressed messages if needed.

**Signature**:
```python
@staticmethod
def grpc_decode(data: bytes) -> Union[Tuple[Dict, Dict], List[Tuple[Dict, Dict]]]
```
- Returns:
    - A single tuple `(decoded_data, typedef)` for one message,
    - Or a list of tuples `[(decoded_data1, typedef1), (decoded_data2, typedef2), ...]` for multiple messages.
- **Note**: There is no separate grpc_stream_decode because grpc_decode already handles multi-message streams.

This design allows consistent encoding/decoding of both **single Protobuf messages** and **streamed gRPC messages** in a unified interface.


---


# 7.ScrapyRunner
This module provides **two ways to start Scrapy spiders**:
1. **ScrapyRunner**: Launches spiders via subprocess mode, using the Scrapy CLI.
2. **InlineScrapyRunner**: Launches spiders via the Scrapy API (`CrawlerRunner`), with options for process- or thread-based execution.

## 7.1 ScrapyRunner Class
This class uses **subprocess mode** to start Scrapy spiders.
It is the simplest way to run spiders, with each spider running in an independent child process, isolated from others. Suitable for batch execution and cross-platform usage.

### 7.1.1 get_all_spider_names
**Purpose**: Retrieve all spider names recognized by the Scrapy project.
**Returns**: `List[str]`

Example:
```python
runner = ScrapyRunner()
spiders = runner.get_all_spider_names()
print(spiders)
```

### 7.1.1 run_all_spiders
**Purpose**: Start multiple spiders in batch.

**Parameters**:
- spiders: `Union[List[str], None]` — List of spider names to run. If `None`, all spiders in the project will be started.

**Behavior**:
- Each spider runs in its own `multiprocessing.Process`.
- The child process executes the Scrapy CLI (`execute(["scrapy", "crawl", spider_name])`), initializing the reactor and logging system automatically.

### 7.1.1 run_spider
**Purpose**: Start a single spider.

**Parameters**:
- spider_name: str — The name of the spider to start.

**Behavior**:
- Runs the spider in a separate child process.
- The child process inherits the parent’s stdout/stderr, so logs are displayed in the terminal by default.
- You can configure Scrapy settings (`LOG_FILE`) to redirect logs to files if needed.

## 7.2 InlineScrapyRunner Class
This class uses **Scrapy API mode** (`CrawlerRunner`) to launch spiders.
Methods and parameters are similar to `ScrapyRunner`, with an additional `use_process` parameter to choose execution mode.

**Features**
- **Process mode (default `use_process=True`)**
    - Each spider runs in an independent child process.
    - Equivalent in behavior to `ScrapyRunner`: isolated reactor, logging controlled by Scrapy settings.

- **Thread mode (`use_process=False`)**
    - All spiders run in the same process using a single `CrawlerRunner` and reactor.
    - Non-blocking to the main thread, allowing other tasks to continue.
    - **Note**: In thread mode, all spiders should be submitted at once to avoid `ReactorNotRestartable` errors.

**Methods**
- **get_all_spider_names()**
    - Retrieves all spider names (same as `ScrapyRunner`).

- **run_all_spiders(spiders: List[str]=None, use_process: bool=True)**
    - Starts multiple spiders, with optional process or thread mode.

- **run_spider(spider_name: str, use_process: bool=True)**
    - Starts a single spider, with optional process or thread mode.

**✅ Summary**
- **ScrapyRunner**: Simplest execution method, each spider runs in an independent child process, similar to running the CLI, cross-platform and stable.
- **InlineScrapyRunner**: Flexible execution, suitable for embedding spiders in Python programs, supports non-blocking threads or independent processes, allowing centralized management.


---


# 8.Fd
Provides static utilities to inspect file descriptor / handle usage of the current process.

## 8.1 get_max_fd
**Purpose**: Retrieve the maximum number of file descriptors (FDs) or handles the current process can open.

**Platform Behavior**:
- **Windows**: Uses CRT `_getmaxstdio`.
- **Linux/macOS**: Uses `resource.RLIMIT_NOFILE`.

**Returns**: `int` – Maximum FD count.

## 8.1 get_used_fd
**Purpose**: Get the number of FDs / handles currently in use by the process.

**Platform Behavior**:
- **Windows**: Uses `psutil.Process().num_handles()`.
- **Linux/macOS**: Counts entries in `/proc/self/fd` (fallback `-1` if not accessible).

**Returns**: `int` – Number of used FDs, or `-1` if unknown.

## 8.3 print_fd_info
**Purpose**: Print a quick summary of the current process FD usage.

**Output Example**:
```python
[FDUtil] Max FD: 1024, Used FD: 42
```

**Usage**:
```python
from scrapy_cffi.utils.fd import FDUtil

FDUtil.print_fd_info()
```

---


# 9.envConfig
Utilities to convert between `SettingsInfo` objects and `.env` files.

## 9.1 settings_to_env
**Purpose**: Serialize a `SettingsInfo` object (or similar Pydantic-like object) into a `.env` file.

**Current behavior**:

- Nested Pydantic models use `PARENT__FIELD` keys.
- Dictionaries and lists use indented, quoted multiline JSON.
- Boolean and numeric scalar types remain unquoted.
- Classes use stable dotted import paths; `None` values are skipped.

**Legacy representation still accepted by the loader**:
- `dict` and `list` fields → JSON strings
- `bool` → `'true'` / `'false'`
- Special `ComponentInfo` fields → empty JSON `'{}'`
- `None` values → skipped

**Parameters**:
- `obj: Any` – Object to serialize
- `env_path: Union[str, Path]` – Destination `.env` file

**Example**:
```python
from scrapy_cffi.utils import settings_to_env
from scrapy_cffi.settings import SettingsInfo

config = SettingsInfo()
settings_to_env(config, ".env.dev")
```

Example output:

```dotenv
LOG_INFO__LOG_LEVEL='INFO'
REDIS_INFO__SENTINELS='[
  ["redis-1", 26379],
  ["redis-2", 26379]
]'
```

## 9.2 env_to_settings
**Purpose**: Load a `.env` file and convert it into an instance of the specified class (e.g., `SettingsInfo`).

**Current behavior**:

- Parses compact or multiline JSON into dictionaries and lists.
- Reconstructs nested models from `__` keys.
- Accepts old compact JSON and unprefixed field names.
- Applies matching `SCRAPY_CFFI_` process variables last.

**Legacy behavior retained for compatibility**:
- Automatically parses JSON strings into `dict` / `list`
- Converts `'true'` / `'false'` to bool
- Converts numeric strings to `int` / `float`
- Restores `ComponentInfo` fields from dict

**Parameters**:
- `env_path: Union[str, Path]` – Path to the `.env` file
- `cls: Type[Any]` – Target class type to instantiate

**Returns**: An instance of `cls` with all fields populated from the `.env`.

**Example**:
```python
from scrapy_cffi.utils import env_to_settings
from scrapy_cffi.settings import SettingsInfo

config = env_to_settings(".env.dev", SettingsInfo)
print(config.TEST_DATA)
```

Use `load_env_settings(existing_settings, env_path=".env")` when Python has
already assembled developer defaults that the operational file should overlay.
