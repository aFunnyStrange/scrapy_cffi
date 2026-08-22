# 工具函数

[English](../../en/usage/9-util.md) | 简体中文

`scrapy_cffi.utils` 使用惰性导出，导入工具模块不会启动 Crawler，也不会强制加载数据库、MQ 或媒体可选依赖。

## 1. 并发

### `run_coroutine_in_new_loop(coro, ...)`

在新线程的新事件循环中执行 Coroutine，并异步等待结果。适合必须隔离事件循环的边界；普通应用优先复用当前循环。

### `run_coroutine_in_thread(coro, ...)`

从同步代码启动线程执行 Coroutine，返回可等待/查询的 Future 包装。不要用它绕过本来可以直接 `await` 的调用。

### `ProcessTaskManager`

`ProcessTaskManager(max_workers=2)` 为短时、可等待任务提供有界进程池。构造时
不会创建 Executor 或子进程，第一次 `await manager.run(...)` 才懒启动。Spider
可直接使用 `await self.run_in_process(func, **kwargs)`；Crawler 只在首次调用后
持有 Manager，并在 shutdown 时关闭。`PROCESS_POOL_MAX_WORKERS` 控制上限。
函数与参数必须可 Pickle，Worker 函数应定义在模块顶层，不能传入父进程的连接池。
取消只能阻止排队任务，不能安全抢占 Worker 中已经执行的 Python，因此这里只适合
短任务；常驻多进程调度仍应放在 `runner.py`。

### `ProcessManager`

提供更高层的多进程生命周期管理。多进程日志应通过集中 Listener 汇聚，多个进程不得直接写同一个文件。

### `FFmpegProcessManager`

`FFmpegProcessManager` 是独立工具，不是 Crawler 内置服务。它没有常驻
Worker 循环，只有调用 `create()` 或 `run()` 时才会创建子进程。短任务可以
直接在 Spider 内等待：

```python
from scrapy_cffi.utils.ffmpeg import FFmpegProcessManager

manager = FFmpegProcessManager(max_processes=2)
result = await manager.run(
    "-i", input_path,
    "-frames:v", "1",
    output_path,
    timeout=30,
)
assert result.succeeded
await manager.close()
```

`FFmpegProcessManager.from_settings(settings)` 读取 `FFMPEG_MAX_PROCESSES`
和 `FFMPEG_EXECUTABLE`；`MediaProbe.from_settings(settings)` 另外读取
`FFPROBE_EXECUTABLE`。这些构造方法同样不会立即启动子进程。

命令始终通过 `asyncio.create_subprocess_exec()` 和结构化参数序列启动，不会
交给 shell 解析或展开。这样可以阻止 shell 注入，但不代表任意 FFmpeg 参数都
是安全的。可执行文件、输入输出路径、URL、协议和选项都应属于可信的应用配置；
不要把 HTTP、消息队列或抓取结果中的原始值直接作为命令。接收不可信媒体引用的
应用应自行校验允许的协议和路径。框架不会注入一份不完整的 FFmpeg 参数白名单或
`protocol_whitelist`，以免悄悄改变合法任务的行为。

需要自行持有进程时使用 `create()`：

```python
process = manager.create("-i", input_path, output_path)
await process.wait_started()
print(process.task_id, process.pid, process.state)
result = await process.stop()
```

Manager 使用 asyncio Semaphore 限制实际存活的操作系统进程数，
`max_processes=None` 表示不限量。Handle 可识别 `QUEUED`、`STARTING`、
`RUNNING`、`STOPPING`、`SUCCEEDED`、`FAILED`、`CANCELLED`、`KILLED`
状态。Handle 会保留自己的终态结果，但 Manager 不持久化历史。

长期拉流或录制应在生成项目的 `runner.py` 中自行创建、监控和关闭，Crawler
不会接管或重启这些进程。Windows 的 asyncio 子进程要求 Proactor loop；生成
项目为了默认 curl_cffi 开发体验仍保留 `WindowsSelectorEventLoopPolicy`，使用
FFmpeg 子进程的项目需要在创建事件循环前显式切换为
`WindowsProactorEventLoopPolicy`，框架不会自动修改该策略。

## 2. 日志

### `init_logger(log_info, logger_name)`

按 `LogInfo` 创建或复用 Logger，支持 Stream、文件、短名称 Formatter、编码和级别配置。

```python
from scrapy_cffi.settings import LogInfo
from scrapy_cffi.utils import init_logger

logger = init_logger(
    LogInfo(LOG_LEVEL="INFO", LOG_FILE="logs/app.log"),
    logger_name=__name__,
)
```

### 多进程日志

`start_multiprocess_log_listener` 在拥有者进程读取日志队列并输出；子进程使用 `init_logger_multiprocessing` 安装 `QueueHandler`。

```python
listener = start_multiprocess_log_listener(log_queue, log_info)
child_logger = init_logger_multiprocessing(log_queue, logger_name=__name__)
```

关闭时由创建 Listener 的进程发送停止信号并 Join；不要让子进程关闭共享 Listener。

## 3. 媒体信息

媒体工具属于可选能力：

```bash
pip install "scrapy_cffi[media]"
```

| 函数 | 说明 |
| --- | --- |
| `guess_content_type(byte_data)` | 基于内容推断 MIME，优先使用 `filetype` |
| `get_image_info_from_bytes(image_bytes)` | 直接从 bytes 获取图片格式、尺寸等信息 |
| `get_video_info_from_bytes(video_bytes)` | 从视频 bytes 获取元数据，依赖可用解析后端 |
| `get_image_info_from_tempfile(image_bytes)` | 兼容旧名称，当前直接使用 Pillow 内存解析 |
| `get_video_info_from_tempfile(video_bytes)` | 兼容旧名称，通过受控临时文件与 hachoir 解析 |

媒体模块按函数懒加载 `filetype`、Pillow 和 hachoir；导入框架或媒体模块本身
不会强制安装全部可选库。在 Spider 内调用同步解析库时，使用
`inspect_image_bytes_async()` 或 `inspect_video_bytes_async()`，它们通过
`asyncio.to_thread()` 避免阻塞当前 loop。

音视频统一推荐异步 `MediaProbe`。它只拥有短时 ffprobe 子进程，通过
`max_processes` 限制同时存活数量，不注册为 Crawler 服务或 `TaskManager`
任务，也没有 Worker 循环：

```python
from scrapy_cffi.utils.media import MediaProbe

# 重复使用时由 runner.py 创建并注入用户代码。
probe = MediaProbe(max_processes=2)
audio = await probe.probe_bytes(response.content, input_format="wav")
print(audio.duration, audio.audio_streams[0].sample_rate)
await probe.close()
```

一次性任务可直接调用 `probe_media_bytes()` 或
`get_audio_info_from_bytes_async()`。长时间拉流仍应在 `runner.py` 使用
`FFmpegProcessManager.create()`，由用户入口负责监控、重启和关闭。

临时文件版本会清理自己创建的文件。大体积媒体不应通过 MQ 传递，应存储到对象存储或其他持久 Blob Store，并在队列里只传引用。

## 4. JSON 提取

### `extract_nested_objects(data, key)`

递归查找嵌套 dict/list 中指定 Key 对应的对象，适合结构已知但层级不固定的 JSON。

### `JSONScanner`

从混合文本扫描 JSON Object/Array，支持按 Key 查找和 Key Chain 逐层提取。用于页面脚本或响应中嵌入的 JSON。

```python
from scrapy_cffi.utils.jsonLoad import extract_json_chain

items = extract_json_chain(
    response.text,
    keys=["payload", "items"],
    strict_level=2,
)
```

`JSONExtractor` 是底层内部实现；用户代码优先使用 `JSONScanner`、`extract_json_chain` 或 `HttpResponse` 上的同名方法。严格级别越高，容错解析越积极；异常文本应记录有限样本，避免把完整敏感响应写入日志。

## 5. Protobuf 与 gRPC

`ProtobufFactory` 统一暴露：

- `protobuf_encode(data, typedef)` / `protobuf_decode(payload)`；
- `grpc_encode(data, typedef, is_gzip=False)`；
- `grpc_stream_encode(stream, is_gzip=False)`；
- `grpc_decode(payload)`。

```python
from scrapy_cffi.utils import ProtobufFactory

encoded = ProtobufFactory.protobuf_encode(data, typedef)
decoded_typedef, decoded = ProtobufFactory.protobuf_decode(encoded)
```

安装 `scrapy_cffi[protobuf]` 后使用 Rust 加速 Codec；纯 Python 回退必须保持相同输入、输出、异常与 Wire Format。

## 6. Scrapy 兼容 Runner

`ScrapyRunner` 通过子进程启动传统 Scrapy 项目：

- `get_all_spider_names()`：列出项目 Spider；
- `run_all_spiders(spiders=None)`：顺序/按实现启动多个 Spider；
- `run_spider(spider_name)`：启动一个 Spider。

`InlineScrapyRunner` 用于受控的线程或进程组合。它是兼容工具，不改变 `scrapy_cffi` 自身 Runner 的生命周期契约。

## 7. 文件描述符诊断

`FDUtil.get_max_fd()` 读取系统可用 FD 上限，`get_used_fd()` 获取当前使用量，`print_fd_info()` 输出诊断信息。该功能适合连接泄漏排查；Windows 与 Unix 的可观测字段可能不同。

## 8. Settings 与环境变量

### `settings_to_env(obj, env_path)`

把 Pydantic 配置递归写成 `.env` 形式。输出可能包含连接信息，生成文件应保持本地且被 Git 忽略；示例文件必须脱敏。

### `env_to_settings(...)` / `load_env_settings(...)`

读取 `.env` 与进程环境并构建配置。进程环境优先于文件值，嵌套字段会做深度合并。

```python
from scrapy_cffi.utils.envConfig import env_to_settings
from scrapy_cffi.settings import SettingsInfo

settings = env_to_settings(SettingsInfo, ".env")
```

不要记录密码、Cookie、Token、Authorization Header 或完整私有载荷。

## 10. 异步友好的邮件工具

`Email` 构造时只保存 SMTP 配置，不会立即联网。`send_async()` 与 `send_text_async()` 通过 `asyncio.to_thread()` 隔离不可避免的同步 `smtplib` 调用，并在一次发送后关闭连接。

```python
from scrapy_cffi.utils.email import Email

sender = Email(
    "smtp.example.com",
    465,
    "crawler@example.com",
    "authorization-code",
)
await sender.send_text_async(
    "Crawler finished",
    "The run completed.",
    ["ops@example.com"],
)
```

需要根据信号发送汇总时，显式注册 `EmailNotificationExtension`；仅导入工具不会自动启用 Extension。

## 9. 其他常用工具

- `do_sha1(data)`：SHA1 Hex Digest；
- `create_uniqueId()`：生成唯一 ID；
- `do_otp(...)`：生成一次性密码；
- `get_node(nodes, fingerprint)`：Jump Consistent Hash 节点选择，用于去重键亲和性，不是 Worker 负载均衡；
- `load_object(path)`：按导入路径加载对象；
- `to_scrapy_settings_py`、`load_settings_from_py`、`convert_to_toml`：配置格式兼容；
- `cancel_all_tasks`：取消并等待当前循环拥有的任务，只能由事件循环所有者调用。
