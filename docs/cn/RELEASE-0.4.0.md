# scrapy_cffi 0.4.0

[English](../en/RELEASE-0.4.0.md) | 简体中文

0.4 建立稳定的 Platform 与外部资源边界，并加入增量 HTTP/SSE 响应。

## HTTP Platform

Crawler Session 与 Downloader 依赖框架自有异步 Protocol。`CurlCffiHttpSession` 是默认适配器，隔离 `curl_cffi` 0.7.4—0.15 的 API 差异；`HTTP_SESSION_FACTORY` 可注入其他兼容传输。

## 流式响应与 SSE

`HttpRequest(stream=True)` 返回 `StreamResponse`，提供 `aiter_bytes`、`aiter_lines`、`aiter_sse` 与幂等 `aclose`。流在回调结束、替换、取消或关闭时释放 Downloader 容量；SSE 默认缓冲上限是 1 MiB。

## 外部资源架构

```text
Crawler / Pipeline / Spider
  -> ResourceService
  -> Repository Protocol 与实现
  -> 一次性 Infra 客户端
  -> 供应商驱动
```

`ResourceSlot` 持有一代可替换客户端。`RetryPolicy` 在 Repository 之上执行有界、可取消恢复，并合并同一资源代际的并发失败。Infra 不持有 Crawler 停止事件、重试装饰器或重连控制器。

## 破坏性清理

移除了旧 `scrapy_cffi.databases`、`scrapy_cffi.mq`、`utils.reconnect` 以及六个具体 `*Manager` 属性。支持的公共路径为：

- `scrapy_cffi.config`：Pydantic 配置模型；
- `scrapy_cffi.infra.<system>`：有意的一次性驱动访问；
- `scrapy_cffi.repo`：稳定存储与队列语义；
- `scrapy_cffi.service`：生命周期和恢复扩展；
- `scrapy_cffi.build_resource_service`：直接使用与测试的组合入口。

发行测试覆盖 Memory、Redis、RabbitMQ、Kafka、Cookie 持久化、非持久化清理、Ctrl+C、HTTP/WebSocket、Stream/SSE、Python 3.9 以及多个 `curl_cffi` 版本。
