# scrapy_cffi 0.4.3：明确运行时与资源边界

[English](../en/RELEASE-0.4.3.md) | [简体中文](../cn/RELEASE-0.4.3.md)

0.4.3 明确了并发、Session 状态、原生运行时激活以及用户组件的资源边界，同时保留既有的全局安全默认值。

## 并发与 Session 限制

三个配置分别控制不同层级：

- `MAX_GLOBAL_CONCURRENT_TASKS=300`：限制单个 Engine 管理的全部任务。
- `MAX_CONCURRENT_REQ=None`：Downloader 默认不增加局部并发限制。
- `SESSION_REQUESTS_PER_SECOND=None`：默认不限制每个 Session 的请求启动频率。

应用可以设置统一的 Session 频率，也可以通过 `hooks.session` 单独配置某个 Session。显式 `None` 始终表示不限速。

## 超时异常回传

请求超时现在会转换为框架自有的类型化异常并传给请求 errback。请求还可以单独覆盖重试次数和重试间隔，因此 Spider 无需替换 Downloader 就能实现用户级追踪和恢复逻辑。

## 原生运行时与 impersonate

`scrapy_cffi.platform.curl_native` 负责进程级、ABI 兼容的 curl wrapper 激活。优先使用 `CURL_CFFI_RUNTIME_DIR` 选择运行时；`CURL_CFFI_NATIVE_DIR` 继续作为兼容别名。

请求上的 `impersonate` 仍是唯一的 Profile 选择接口。激活原生运行时不会为全部请求自动选择浏览器身份。

## 资源与持久化状态

Spider、Pipeline、Interceptor、Extension 和信号钩子都可以使用同一资源服务，访问已配置的 SQL、MongoDB、Redis、RabbitMQ 或 Kafka。Pipeline 不再是唯一允许访问数据资源的组件。

Redis Scheduler 默认只持久化任务状态。Cookie 和 Client Hints 的持久化需要显式开启。账号与设备记录应存放在持久化数据库中，队列消息只携带轻量任务引用和 `session_id`。

## 配置与 CLI

`.env` 和进程环境变量可以直接使用 Pydantic 字段名，包括 `REDIS_INFO__URL` 这样的嵌套名称；历史 `SCRAPY_CFFI_` 前缀仍然兼容。

彩色 Banner 只在根级 `scrapy-cffi -h` 和 `scrapy-cffi banner` 展示，子命令帮助保持简洁。

FFmpeg 多进程不属于本次发布范围，留待后续版本处理。
