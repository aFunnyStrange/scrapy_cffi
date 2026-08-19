# scrapy_cffi 0.3.3

[English](../en/RELEASE-0.3.3.md) | 简体中文

发布日期：2026-08-01。

0.3.3 强化了分布式爬取的可恢复性、本地基础设施验证和发行包边界：

- Redis、RabbitMQ、Kafka Scheduler 支持受控关闭和非持久化状态清理。
- RabbitMQ 与 Kafka 请求队列继续使用 Redis 分布式去重；Kafka 分离启动请求与增量请求。
- Session Cookie 与请求状态采用有界序列化和压缩，降低 Redis 内存压力。
- 数据库和 MQ 通过显式、IDE 可见的 Manager API 实现单飞传输恢复。
- `scrapy-cffi infra` 管理一次性的单机、Sentinel 与 Cluster 开发拓扑，不与生产部署耦合。
- `scrapy-cffi test single|sentinel|cluster|all` 提供可重复的 Demo、中断、清理和日志验证。

Python 3.9—3.13 覆盖所有声明的数据库和 Broker extra；Python 3.14 的 MySQL 支持仍取决于 `asyncmy` 的兼容发行版。`curl_cffi` 的已验证范围为 `>=0.7.4,<=0.13.0`。完整历史见 [CHANGELOG](../../CHANGELOG.md)。

