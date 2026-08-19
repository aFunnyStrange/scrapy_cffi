# 1. 拦截器

[English](../../en/usage/4-interceptors.md) | 简体中文

`scrapy_cffi` 使用 Interceptor 表示与 Scrapy Middleware 对应的扩展点。`BaseInterceptor` 是 `DownloadInterceptor` 与 `SpiderInterceptor` 的共同基类。

| 属性 | 说明 |
| --- | --- |
| `settings` | 当前 Crawler 配置 |
| `resources` | 带类型的 `ResourceService`，按配置提供 Redis、RabbitMQ、Kafka、SQL、MongoDB Repository |

```python
RequestType = Union[HttpRequest, WebSocketRequest]
ResponseType = Union[HttpResponse, WebSocketResponse]
```

## 2. DownloadInterceptor

### `request_intercept(request, spider)`

在请求到达 Downloader 前执行，对应 Scrapy `process_request`：

- 返回 `None`：不修改，继续下一拦截器；
- 返回 `Request`：立即中断链并重新调度；指纹未变化时仍会去重，确需绕过时设置 `dont_filter=True`，否则容易形成无限循环；
- 返回 `Response`：跳过 Downloader，直接交给 Spider；
- 返回 `BaseException`：进入 `exception_intercept`。

### `response_intercept(request, response, spider)`

Downloader 返回后执行，对应 `process_response`。返回 `Request` 时重新调度；返回 `None` 继续链；返回 `Response` 直接交给 Spider；返回异常时进入异常链。

### `exception_intercept(request, exception, spider)`

对应 `process_exception`。可返回 Request 重新调度、返回 Response 恢复、返回 `None` 继续异常链，或返回异常交给 Engine。Spider 定义了 Errback 时由 Errback 处理，否则异常被终止。

## 3. SpiderInterceptor

```python
ResultType = Union[Request, Item, Dict, None]
```

### `process_spider_input(response, spider)`

响应或异常进入 Spider 前执行。`None` 表示继续；`BaseException` 中断链并进入 Errback（若存在）。

### `process_spider_output(response, result, spider)`

处理 Spider 产出的 Request、Item、Dict 或 `None`。返回异常时进入 `process_spider_exception`；返回 `None` 会丢弃当前结果。

### `process_spider_exception(response, exception, spider)`

处理 Spider 回调异常。Request 会重新调度；Item/Dict 进入 Pipeline；`None` 继续异常链；返回异常则终止并丢弃。

