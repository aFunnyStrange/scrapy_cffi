# 请求与响应对象

[English](../../en/usage/3-internet.md) | 简体中文

## 1. Request 公共字段

`Request` 是 `HttpRequest`、`MediaRequest` 与 `WebSocketRequest` 的序列化基类。主要字段：

| 字段 | 说明 |
| --- | --- |
| `session_id` | Session 或 Session Group 标识 |
| `url`、`params` | URL 与查询参数；参数使用 `urlencode(..., doseq=True)` 合并 |
| `headers`、`cookies`、`proxies` | 请求 Header、Cookie、代理 |
| `timeout` | 单次传输超时，默认 30 秒 |
| `max_retry_times` | 当前请求的总尝试次数；为空时继承 `MAX_REQ_TIMES` |
| `retry_delay` | 当前请求的重试间隔秒数；为空时继承 `DELAY_REQ_TIME`，允许 0 |
| `allow_redirects`、`max_redirects` | 重定向策略 |
| `verify` | TLS 证书校验设置 |
| `impersonate` | 每请求 curl Profile/别名，必须显式选择 |
| `ja3`、`akamai` | 低层指纹参数 |
| `meta` | 贯穿 Request/Response 的用户元数据 |
| `dont_filter` | 当前请求是否跳过去重 |
| `callback`、`errback` | 成功/失败回调；持久化时保存方法名 |
| `desc_text` | 日志或诊断描述 |
| `no_proxy` | 当前请求绕过代理 |
| `stream` | 启用实时 HTTP Stream |

`to_bytes()` 使用有界状态 Codec 保存类名、回调标识与二进制字段；`from_bytes()` 恢复具体 Request 子类。这一格式用于 Scheduler 持久化，应用不应改写内部标记。

### 超时重试与 Errback

HTTP、Stream 和 WebSocket 的传输超时在重试耗尽后统一转换为
`RequestTimeoutError`，并进入当前 Request 的 `errback`。异常提供
`request`、`exception`、`timeout` 和 `attempts`：

```python
from scrapy_cffi.exceptions import RequestTimeoutError

yield HttpRequest(
    url=url,
    timeout=10,
    max_retry_times=3,
    retry_delay=0.5,
    callback=self.parse,
    errback=self.on_error,
)

async def on_error(self, failure):
    if isinstance(failure, RequestTimeoutError):
        self.logger.warning(
            "task=%s timeout attempts=%s",
            failure.request.meta.get("task_id"),
            failure.attempts,
        )
```

## 2. HttpRequest

### HTTP/3 / QUIC（实验性请求支持）

HTTP/3 是单次请求的传输偏好，不会创建类似 WebSocket 的后台监听任务：

```python
from scrapy_cffi.internet import HttpRequest
from scrapy_cffi.platform import HttpVersion

yield HttpRequest(
    url="https://example.com/",
    http_version=HttpVersion.HTTP_3_ONLY,
    callback=self.parse,
)
```

`HTTP_3` 允许 curl 回退到较早 HTTP 版本；`HTTP_3_ONLY` 在 curl 构建、UDP
路径、服务器或代理无法建立 QUIC 时明确失败。生成 Demo 提供最小 `aioquic`
HTTP/3 Server 与爬虫请求示例。当前框架尚未暴露 Server Push、QUIC 单向流
回调、Datagram、WebTransport 或 MASQUE 代理控制，也不会伪造全局监听 Task。
传统 HTTP 代理通常不能隧道 UDP；经代理保持 HTTP/3 需要代理与 curl 构建同时
支持 CONNECT-UDP/MASQUE。

在公共字段外增加 `method`、`data` 与 `json`。传 `json` 时框架紧凑序列化并补充 `Content-Type: application/json`；显式 Header 不应被无条件覆盖。

```python
yield HttpRequest(
    url="https://example.com/api",
    method="POST",
    json={"page": 1},
    headers={"Accept": "application/json"},
    callback=self.parse,
)
```

### Streaming 与 SSE

`HttpRequest(stream=True)` 返回 `StreamResponse`，而不是一次性缓冲完整正文：

```python
async def parse_stream(self, response):
    async for event in response.aiter_sse():
        yield {"event": event.event, "data": event.data}
```

`StreamResponse` 提供：

- `aiter_bytes(chunk_size=None)`：异步读取字节块；
- `aiter_lines()`：异步读取文本行；
- `aiter_sse(max_event_size=1048576)`：解析有界 SSE Event；
- `aclose()`：幂等关闭 Stream 并释放 Downloader 容量。

框架会在回调成功、失败、替换、取消或 Crawler Shutdown 时关闭仍由它拥有的 Stream。应用接管 Stream 后也应按消费契约关闭；SSE 单事件默认上限为 1 MiB。

### Protobuf 与 gRPC 编码

`protobuf_encode(typedef)` 把 `data` 编码为 Protobuf。`grpc_encode(typedef_or_stream, is_gzip=False)` 支持单消息字典或消息流列表；方法修改 Request 并返回自身，便于链式调用。

```python
request = HttpRequest(
    url=url,
    method="POST",
    data={"id": 1},
    headers={"Content-Type": "application/protobuf"},
).protobuf_encode(typedef)
```

Content-Type 包含 `protobuf` 或 `grpc` 而 `data` 不是 bytes 时，框架会发出 Warning。

## 3. WebSocketRequest

主要扩展字段：

| 字段 | 说明 |
| --- | --- |
| `websocket_id` | 现有连接 ID；非空表示后续连接操作 |
| `send_message` | `WebSocketMsg` 或其列表；默认发送二进制 `ping` |
| `ping_data` | 可选心跳 `WebSocketMsg` |
| `ping_interval` | 心跳间隔，默认 15 秒 |

```python
from scrapy_cffi.internet import WebSocketRequest
from scrapy_cffi.models import WebSocketMsg
from scrapy_cffi.platform import WebSocketFlag

yield WebSocketRequest(
    url="wss://example.com/ws",
    send_message=WebSocketMsg(
        data=b"hello",
        flags=WebSocketFlag.BINARY,
    ),
    callback=self.on_frame,
)
```

初始 Request 在第一次 Receive 前发送 `send_message`。Listener 直接把 Frame 分发给回调并等待事件；不通过结束字符串判断关闭。后续发送携带 `websocket_id`，连接已关闭时进入 `SessionEndError`，不会自动打开替代长连接。

`grpc_stream_encode()` 要求消息数据已经是 bytes，并把多条消息合并为一个 Binary `WebSocketMsg`。

## 4. MediaRequest

继承 `HttpRequest`，用于图片、音频和视频的顺序 Range 下载。它只在现有
asyncio loop 内逐段请求，不创建并发任务、线程或进程。`media_size > 0` 时按
inclusive byte range 顺序合并内容；`media_size == 0` 时退化为一次普通请求。
`max_media_size` 可选地限制内存中允许保存的媒体大小，原始 Headers 不会被修改。
它同样支持显式 `impersonate`、Session、回调与 Scheduler 持久化。

## 5. Response 公共字段

`Response` 保存 `session_id`、`raw_response`、`meta`、去重标记、Callback、Errback、描述、原始 Request 与扩展参数。`meta` 来自对应 Request，适合传递任务 ID 等轻量上下文，不应塞入大体积正文。

## 6. HttpResponse

常用属性为 `status_code`、`content`、`text`、`raw_response` 与 `selector`。根据 Content-Type 自动选择 HTML、XML 或普通解析模式。

| 方法 | 说明 |
| --- | --- |
| `xpath(query)` | XPath 选择 |
| `css(query)` | CSS 选择 |
| `re(pattern)` | 正则提取 |
| `json()` | 解析标准 JSON |
| `extract_json(key="", re_rule="")` | 从普通文本或指定区域提取 JSON |
| `extract_json_strong(key="", strict_level=2, re_rule="")` | 容错提取带注释、引号问题或嵌套 JSON 字符串的内容 |
| `extract_json_chain(keys, strict_level=2, re_rule="")` | 按 Key 链逐层提取 |
| `protobuf_decode()` | 返回 Protobuf 类型定义与解码数据 |
| `grpc_decode()` | 解码单条或流式 gRPC Frame |

```python
async def parse(self, response):
    title = response.css("title::text").get()
    data = response.extract_json_chain(["payload", "items"])
    yield {"title": title, "items": data}
```

## 7. WebSocketResponse

`msg` 是当前 Frame bytes，`websocket_id` 标识连接。`protobuf_decode()` 与 `grpc_decode()` 对当前 Frame 解码。

完成监听时调用：

```python
async def on_frame(self, response):
    if response.msg == b"done":
        response.stop_listening()
        return
    yield {"message": response.msg}
```

`stop_listening()` 幂等设置连接停止事件，是业务完成的真实 WebSocket 信号。Crawler Shutdown 与旧 `CloseSignal` 使用同一事件；接收超时、空队列或 `WS_END_TAG` 都不能冒充关闭。
