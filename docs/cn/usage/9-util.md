# 工具函数

[English](../../en/usage/9-util.md) | 简体中文

`scrapy_cffi.utils` 使用惰性导出，导入工具模块不会启动 Crawler，也不会强制加载数据库、MQ 或媒体可选依赖。

## 1. 并发

### `run_coroutine_in_new_loop(coro, ...)`

在新线程的新事件循环中执行 Coroutine，并异步等待结果。适合必须隔离事件循环的边界；普通应用优先复用当前循环。

### `run_coroutine_in_thread(coro, ...)`

从同步代码启动线程执行 Coroutine，返回可等待/查询的 Future 包装。不要用它绕过本来可以直接 `await` 的调用。

### `ProcessTaskManager`

管理有界子进程任务、结果队列与回收。提交函数和参数必须可序列化；调用者仍负责业务幂等性和外部资源连接，不能把父进程连接池传入子进程。

### `ProcessManager`

提供更高层的多进程生命周期管理。多进程日志应通过集中 Listener 汇聚，多个进程不得直接写同一个文件。

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
| `get_image_info_from_tempfile(image_bytes)` | 必须走文件接口时使用受控临时文件 |
| `get_video_info_from_tempfile(video_bytes)` | 通过临时文件与 ffprobe/解析器读取视频信息 |

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

## 9. 其他常用工具

- `do_sha1(data)`：SHA1 Hex Digest；
- `create_uniqueId()`：生成唯一 ID；
- `do_otp(...)`：生成一次性密码；
- `get_node(nodes, fingerprint)`：Jump Consistent Hash 节点选择，用于去重键亲和性，不是 Worker 负载均衡；
- `load_object(path)`：按导入路径加载对象；
- `to_scrapy_settings_py`、`load_settings_from_py`、`convert_to_toml`：配置格式兼容；
- `cancel_all_tasks`：取消并等待当前循环拥有的任务，只能由事件循环所有者调用。
