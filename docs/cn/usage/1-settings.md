# SettingsInfo 配置参考

[English](../../en/usage/1-settings.md) | 简体中文

`SettingsInfo` 是 Crawler 的显式配置对象。字段使用 Pydantic v2 校验；未知字段只供用户代码使用，框架会发出 Warning。一个 Crawler 共享基础配置，每个 Spider 可通过类属性 `settings_overlay` 覆盖允许的字段。

```python
from scrapy_cffi.settings import SettingsInfo

settings = SettingsInfo(
    MAX_GLOBAL_CONCURRENT_TASKS=300,
    MAX_CONCURRENT_REQ=50,
    ROBOTSTXT_OBEY=True,
)
```

## 1. 通用配置

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `MAX_GLOBAL_CONCURRENT_TASKS` | `300` | Crawler 全局任务上限，使用 `asyncio.BoundedSemaphore`；`None` 表示不设置该边界 |
| `QUEUE_NAME` | `""` | 工作队列前缀；设置后通常解析为 `{QUEUE_NAME}:{spider.name}`，否则为 `{spider.name}_req` |
| `ROBOTSTXT_OBEY` | `True` | 是否读取并遵守 robots.txt |
| `MAX_SCHEDULER_LOOP_NUM` | `10` | Scheduler 并行循环数量，不是完成判据 |
| `SCHEDULER_LOOP_END` | `None` | 已弃用；完成必须由生产者结束和 Engine 自有工作归零驱动 |

## 2. 请求配置

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `USER_AGENT` | `scrapy_cffiBot` | 默认 User-Agent |
| `DEFAULT_HEADERS` | `{}` | 默认 Header |
| `DEFAULT_COOKIES` | `{}` | 默认 Cookie |
| `MAX_CONCURRENT_REQ` | `None` | Downloader 请求并发上限 |
| `USE_STRICT_SEMAPHORE` | `False` | 使用 `BoundedSemaphore` 检查过度 release |
| `TIMEOUT` | `30` | 单次请求超时秒数；属于传输边界，不是 Crawler 生命周期信号 |
| `MAX_REQ_TIMES` | `2` | 失败请求最大尝试次数 |
| `DELAY_REQ_TIME` | `3` | 请求重试延迟秒数 |
| `HTTP_SESSION_FACTORY` | `None` | HTTP Session 工厂或导入路径；为空时使用 `CurlCffiHttpSession` |
| `CURL_CFFI_NATIVE_DIR` | `None` | 自构建 curl 包装目录，只选择进程级原生实现，不代表默认 `impersonate` |
| `INFRA_RETRY_ATTEMPTS` | `3` | 外部资源有界恢复次数，至少 1 |
| `INFRA_RETRY_DELAY` | `1.0` | 外部资源重试间隔秒数 |

`HTTP_SESSION_FACTORY` 应实现框架自有异步 HTTP Protocol。自构建 curl 目录契约见 [0.4.2 说明](../RELEASE-0.4.2.md)。

## 3. 代理

| 字段 | 说明 |
| --- | --- |
| `PROXY_URL` | 同时写入 HTTP/HTTPS 的单一代理 URL |
| `PROXIES` | 协议到代理 URL 的映射 |
| `PROXIES_LIST` | 可供应用或扩展选择的代理列表 |

设置 `PROXY_URL` 时，模型校验后会把 `PROXIES` 规范化为 `{"http": value, "https": value}`。

## 4. 组件配置

| 字段 | 说明 |
| --- | --- |
| `SPIDERS_PATH` | 单 Spider 模式可传类或导入路径；Run-all 模式传 Spider 目录 |
| `SPIDER_INTERCEPTORS_PATH` | Spider Interceptor 配置 |
| `DOWNLOAD_INTERCEPTORS_PATH` | Download Interceptor 配置 |
| `ITEM_PIPELINES_PATH` | Pipeline 配置 |
| `EXTENSIONS_PATH` | Extension 配置 |

组件配置可使用 `ComponentInfo`、`{组件: 优先级}`、列表、类或导入路径。优先级用于确定链顺序；推荐传类对象以保留 IDE 跳转。

```python
from scrapy_cffi.models import ComponentInfo

settings.DOWNLOAD_INTERCEPTORS_PATH = ComponentInfo.from_raw({
    CustomDownloadInterceptor1: 100,
    CustomDownloadInterceptor2: 200,
})
```

## 5. Scheduler 与去重

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `SCHEDULER` | `None` | 显式全局 Scheduler 类/路径；为空时按每个 Spider 类型选择 Memory、Redis、RabbitMQ 或 Kafka Scheduler |
| `DUPEFILTER` | `None` | 自定义去重器类/路径 |
| `SCHEDULER_PERSIST` | `False` | 是否跨运行保留队列、Session 和去重状态 |
| `SCHEDULER_SESSION_KEY` | `None` | 压缩 Session Cookie 的 Redis Hash；为空时使用 `{queue_key}:sessions` |
| `DEDUP_TTL` | `0` | 去重键 TTL；0 表示不自动过期 |
| `INCLUDE_HEADERS` | `[]` | 计算指纹时纳入的 Header 名 |
| `FILTER_KEY` | `cffiFilter` | 去重键前缀 |
| `DONT_FILTER` | `False` | 全局禁用请求去重 |
| `_NEW_SEEN` / `_SENT_SEEN` | 派生值 | 分别为 `{FILTER_KEY}_new_seen` 与 `{FILTER_KEY}_sent_seen`，只读 |

不要为了队列 Spider 混跑而设置全局 `SCHEDULER`；默认逻辑会为每个 Spider 选择正确 Scheduler。`SCHEDULER_PERSIST=False` 时，正常关闭和 Ctrl+C 会清理框架拥有的临时状态。

### `BLOOM_INFO`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `MODE` | `False` | 是否启用 Bloom 模式 |
| `SIZE` | `100_000_000` | Bitmap 位数，必须大于 0 |
| `EXPECTED` | `10_000_000` | 预期元素数量，必须大于 0 |
| `HASH_COUNT` | `0` | Hash 数量；0 表示按参数计算 |

## 6. WebSocket、JavaScript 与日志

`WS_END_TAG="websocket end"` 仅为旧配置兼容。WebSocket 必须通过 `response.stop_listening()`、Crawler Shutdown 或同一停止事件结束，不能依赖队列结束字符串。

`JS_PATH` 可指定 JS 文件目录；`None` 由运行脚本附近的默认目录解析，`False` 可禁用。

`LOG_INFO` 字段：

| 字段 | 默认值 |
| --- | --- |
| `LOG_ENABLED` | `True` |
| `LOG_WITH_STREAM` | `True` |
| `LOG_LEVEL` | `DEBUG` |
| `LOG_FORMAT` | `%(asctime)s [%(name)s] %(levelname)s: %(message)s` |
| `LOG_DATEFORMAT` | `%Y-%m-%d %H:%M:%S` |
| `LOG_FILE` | 空字符串 |
| `LOG_ENCODING` | `utf-8` |
| `LOG_SHORT_NAMES` | `False` |
| `LOG_FORMATTER` | 空字符串 |

`LOG_LEVEL` 只接受 `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`。

## 7. 数据库配置

所有数据库模型都支持 `URL` 或拆分字段 `HOST`、`PORT`、`USERNAME`、`PASSWORD`、`DB`。URL 优先；不要把密码写入日志或提交到仓库。

### RedisInfo

- `MODE`：`single`、`sentinel` 或 `cluster`；
- Sentinel：`SENTINELS`、`MASTER_NAME`、可选 `SENTINEL_OVERRIDE_MASTER`、独立 Sentinel 凭据；
- Cluster：`CLUSTER_NODES`、`CLUSTER_ADDRESS_REMAP`；
- 传输：`CONNECT_TIMEOUT=5.0`、`SOCKET_TIMEOUT=None`、`PROTOCOL=2`、SSL 相关字段。

### RedisStreamConsumerInfo

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `MODE` | `LIST` | List 或 Stream 入口 |
| `STREAM_KEY` | `None` | Stream Key；Spider `redis_key` 可覆盖 |
| `GROUP_NAME` | `None` | Consumer Group |
| `CONSUMER_NAME` | `None` | Consumer 名 |
| `FIELD` | `data` | 载荷字段 |
| `COUNT` | `1` | 单次读取数量 |
| `BLOCK_MS` | `2000` | Broker 读取等待上限，只是传输重试边界，不是完成信号 |
| `GROUP_START_ID` | `0` | 创建 Group 的起始 ID |
| `READ_ID` | `>` | 默认读取新消息 |
| `MKSTREAM` | `True` | 创建 Group 时允许创建 Stream |
| `AUTO_ACK` | `True` | 成功交付后的确认策略 |

### SQL 与 Mongo

- `MYSQL_INFO`：默认驱动 `mysql+asyncmy`；
- `POSTGRES_INFO`：默认驱动 `postgresql+asyncpg`；`POSTGRESS_INFO` 只保留为旧拼写兼容；
- SQL Pool：`ECHO=False`、`POOL_PRE_PING=True`、`POOL_SIZE=5`、`MAX_OVERFLOW=10`；
- `MONBODB_INFO`：历史拼写保留的 MongoDB 配置字段。

## 8. 消息队列

`QueueConnectionInfo` 通用字段包括 `DRIVER`、`URL`、`HOST`、`PORT`、`USERNAME`、`PASSWORD`、`MODE` 与 `CLUSTER_NODES`。

### RabbitMQInfo

`VHOST="/"`、`EXCHANGE_NAME="scrapy_cffi"`、`EXCHANGE_TYPE="direct"`、`PREFETCH_COUNT=10`、`DONT_FILTER=False`、`CONNECTION_TIMEOUT=10.0`、`HEARTBEAT=60`。

### KafkaInfo

`CONSUMER_GROUP="scrapy_cffi"`、`PERSISTENT_TIME=7天`、`NUM_PARTITIONS=3`、`REPLICATION_FACTOR=None`、`AUTO_OFFSET_RESET="earliest"`、`CLIENT_ID="scrapy_cffi"`、`REQUEST_TIMEOUT_MS=40000`，并支持 `SECURITY_PROTOCOL`、SASL 与 SSL 文件字段。

## 9. CPY_EXTENSIONS

`CPY_EXTENSIONS.DIR` 指定项目资源目录名，`RESOURCES` 是 `CPYExtension` 列表。完整目录和回退契约见 [CPython 扩展](12-cpython.md)。
