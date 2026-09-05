# scrapy_cffi 0.4.4：轻量异步 Worker 内核

[English](../en/RELEASE-0.4.4.md) | [简体中文](../cn/RELEASE-0.4.4.md)

0.4.4 在保留专项爬虫运行时的同时，开始将 scrapy_cffi 发展为可复用的异步 Worker 内核。框架默认仍只运行一个 asyncio 事件循环，不会隐式引入线程、进程、持久化调度器或 Celery 依赖。

## 短时媒体与进程任务

媒体工具通过可选的跨平台库读取图片、视频和音频元数据。Pillow、hachoir 等同步操作提供了明确的 `asyncio.to_thread()` 异步入口。

`FFmpegProcessManager` 使用 `asyncio.create_subprocess_exec()` 无 shell 启动子进程，限制同时存活的进程数，记录明确状态，保留有界输出尾部，并支持优雅停止后再 terminate/kill。Spider 可以等待短任务；长期拉流仍由应用 `runner.py` 持有，Crawler 不负责重启或监管。

Crawler 持有的 `ProcessTaskManager` 同样是惰性、有界的，仅面向短时、可 pickle 的 CPU 工作。多进程调度仍属于应用层。

## 应用自有资源

项目可以在 settings 中注册 `Resource` 类。运行时创建一个共享实例，按依赖顺序启动，并按相反顺序关闭。Spider、Pipeline、Interceptor、Extension 和信号 Hook 使用同一注册表。

框架只提供生命周期和类型化获取，不虚构统一的 BOS 或厂商 SDK。账号、客户端构造和厂商专有方法仍由用户负责。Pipeline 的 `open_spider()`、`close_spider()` 继续适合管理每个 Spider 的状态，但不再负责共享基础设施。

## 运行状态与可选 Hub

`RunContext` 标识进程实例、单次运行、可选持久化任务及尝试次数。`start_spider_run()`、`start_all_spiders_run()` 返回可等待、可主动停止的 `CrawlerRunHandle`，原有 Runner API 保持兼容。

按需启用的监控扩展报告生命周期、心跳、计数和错误。实验性 FastAPI Hub 保存有界的观测状态，也可以通过用户实现的 `TaskStateProvider` 只读展示应用任务；它不会写入或替代 MySQL/Postgres 中的任务事实。心跳过期只会将可用性标为 `unreachable`，不会伪造完成或失败状态。

可选邮件扩展同样不进入默认热路径。SMTP 连接按需创建，默认发送聚合完成摘要，仅在配置后即时发送错误。

## HTTP/3 边界

`HttpVersion.HTTP_3` 和 `HTTP_3_ONLY` 暴露合格 curl_cffi/libcurl 构建所支持的请求偏好。它并不是通用 QUIC Stream、Datagram、Server Push、回调监听、WebTransport 或代理控制 API。可选 aioquic Demo Server 用于说明和测试当前实验性的单次请求边界。

## 生成项目与兼容性

普通项目和 Demo 都会生成 `project_support/` 拓扑工具。生成的 `runner.py` 包含 `managed_main()` 示例，方便应用将框架运行结果映射到自己持久化的任务状态。

本版本继续支持 Python 3.9、可选依赖惰性导入、有限 Spider 自然结束，以及 Redis、RabbitMQ、Kafka 持续 Spider 的显式关闭。创建发布标签前，会在 Windows 与 WSL Ubuntu 上执行完整的真实生成项目矩阵。
