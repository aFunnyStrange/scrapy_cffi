# 架构路线图

`scrapy_cffi` 的长期定位是轻量异步 Worker 内核。Crawler 是当前第一种、也是能力最完整的专项 Worker 适配；通用资源、线程、子进程与 Server 能力保持独立组合，不会默认塞入 Crawler 热路径。

[English](../en/ARCHITECTURE-ROADMAP.md) | 简体中文

## 当前 0.4 分层模型

```text
runner
  -> Crawler 组合根
  -> core（Engine、Scheduler、Spider、Pipeline）
  -> service（资源生命周期与有界恢复）
  -> repo（存储语义与请求队列语义）
  -> infra（一次性外部系统客户端）
  -> platform（可复用 HTTP 与编解码能力）
```

外部系统适配器按具体系统平行组织：

```text
infra/redis
infra/rabbitmq
infra/kafka
infra/sqlalchemy
infra/mongodb
```

Redis 不归入单一“数据库”或“Broker”类别，因为它同时可以承担去重、Session、List、Stream、协调与缓存职责。

## 已完成

- [x] 建立框架自有的 HTTP、WebSocket 与流式响应 Protocol，并通过 `curl_cffi` 适配器实现。
- [x] `config` 负责 Pydantic 连接模型和拓扑模型。
- [x] `infra` 客户端不持有爬虫状态、重试循环或重连控制器。
- [x] `repo` 负责 Redis 去重、Session、队列语义以及 SQL/Mongo 操作。
- [x] `service.ResourceService` 负责生命周期，`RetryPolicy` 与 `ResourceSlot` 负责有界资源替换。
- [x] `composition.build_resource_service` 同时供 Crawler、直接调用与功能测试使用。
- [x] Scheduler 依赖框架 Protocol，而不是具体 Redis/RabbitMQ/Kafka 客户端。
- [x] Pipeline、Spider 与 Extension 获得同一个带类型的资源服务。
- [x] 已移除旧的 `databases`、`mq` 和 `utils.reconnect` 实现模块。
- [x] 类型化惰性导出兼顾可选依赖隔离与 IDE 跳转。
- [x] Memory、Redis、RabbitMQ、Kafka、持久化、Ctrl+C 清理、Stream 与 SSE 均有测试覆盖。

## 依赖规则

- 下层不得导入 Crawler、Scheduler、Pipeline 或 Service 等上层模块。
- Infra 每次只执行一次原生操作，并原样传播供应商失败。
- Repository 定义可重放边界；原生客户端逃生口仍是明确的一次性调用。
- Service 的恢复必须有界、可取消、可观测，并让同一失败代际只发生一次资源替换。
- 只有 Composition 层可以选择具体外部系统实现。

## 后续工作

- 只有在大体积爬虫产物需要持久化并从队列载荷中分离时，才增加对象存储 Repository。
- 只有在业务需要跨阶段权威状态时，才增加数据库任务状态；不能用 Scheduler 持久化代替业务状态。

## 通用异步 Worker 内核方向

- `runtime.ResourceService` 现在允许通过 `settings.RESOURCES_PATH` 注册用户
  自定义的 `Resource` 子类。
- Resource 按配置顺序启动、反向关闭，并被 Spider、Pipeline、Interceptor
  和 Extension 全局共享。
- 框架不适配对象存储厂商的账号字段和不统一 API；项目 Resource 自己持有
  SDK、配置和领域方法。
- Crawler 是当前已经完整适配的 Worker 类型。只有第二种非爬虫 Worker
  出现真实生命周期需求后，才继续抽象通用 Run Scope 和任务执行协议。
