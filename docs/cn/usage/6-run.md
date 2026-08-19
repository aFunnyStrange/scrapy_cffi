# 1. 运行入口

[English](../../en/usage/6-run.md) | 简体中文

`scrapy_cffi` 是基于 `asyncio` 的全异步框架，不支持 `scrapy crawl ...` 风格命令。事件循环与 KeyboardInterrupt 等顶层异常必须由运行入口统一拥有。

# 2. 标准模式

多数应用直接使用 `run_spider_sync` 或 `run_all_spiders_sync`。同步包装会创建并运行事件循环，调用方不必自己管理 async 生命周期。

# 3. 高级模式

需要接入现有异步、多线程或多进程系统时，使用 `run_spider`、`run_all_spiders` 或 `run_spiders`。跨事件循环共享 asyncio 对象不安全，必须由应用显式处理。

框架提供线程级日志支持；多进程模式下不要让多个进程直接写同一个日志文件，可使用：

```python
from scrapy_cffi.utils import (
    init_logger_multiprocessing,
    start_multiprocess_log_listener,
)
```

# 4. 配置与架构

框架允许一个进程运行多个 Spider，因此不依赖隐式全局配置；运行时显式注入 `SettingsInfo`。兼容工具包括：

- `to_scrapy_settings_py(settings_obj)`：生成 Scrapy 风格配置文本；
- `load_settings_from_py(filepath, auto_upper=True)`：读取 Python 配置；
- `convert_to_toml(py_path, toml_path)`：转换为 TOML；
- `ScrapyRunner`、`InlineScrapyRunner`：通过子进程运行 Scrapy 项目。

单 Spider 的事件流见[生命周期图](../../assets/diagrams/spider-lifecycle.svg)。每个 Spider 拥有自己的 Engine 与 Scheduler；Downloader、拦截器链、Pipeline、Signal 与 ResourceService 由顶层 Crawler 共享，见 [Crawler 结构图](../../assets/diagrams/crawler-structure.svg)。

`run_all_spiders` 在同一线程、事件循环和 Crawler 中运行多个 Spider。有限 Engine 完成时不能停止持续监听的兄弟 Engine；普通 `Spider` 仍使用内存 `Scheduler`，不会因为同组存在 Redis/RabbitMQ/Kafka Spider 就被自动提升。只有显式全局 `settings.SCHEDULER` 才覆盖所有 Spider。

需要同一事件循环内的独立配置与资源时，使用 `run_spiders` 创建多个 Crawler；只有确实需要独立事件循环或进程时才使用线程/进程边界。参见[编排模式图](../../assets/diagrams/orchestration.svg)。

高并发部署可以让多个 Worker 共享 Broker 入口和按 Spider 命名空间隔离的去重存储，参见[集群部署图](../../assets/diagrams/cluster-deployment.svg)。本地 `infra` 拓扑只模拟依赖；生产 Worker 直接连接真实数据库与 MQ。

相关内容：[多 Crawler](14-multi-spider-resources.md)、[独立工具](13-standalone-tools.md)、[去重](15-deduplication.md)。
