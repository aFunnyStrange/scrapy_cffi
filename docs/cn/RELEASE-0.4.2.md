# scrapy_cffi 0.4.2：自构建 curl Profile

[English](../en/RELEASE-0.4.2.md) | 简体中文

0.4.2 把原先独立本地包中的请求 Profile 适配器整合进框架。框架可以选择兼容的自构建 `curl-impersonate` 包装，但每个请求仍必须显式选择自己的 Profile。

## 运行时边界

`CURL_CFFI_NATIVE_DIR` 选择进程级原生实现。目录必须包含与当前 Python ABI 匹配的 `_wrapper`，以及相邻的 Windows DLL 或 Linux 共享库依赖。它不是“默认模拟浏览器”的配置。

该适配器只在运行时生效：原生二进制和具体 Profile 定义不会打入 `scrapy_cffi` wheel，也不是构建依赖。配置为空时继续使用官方安装的 `curl_cffi`。

```python
from pathlib import Path
from scrapy_cffi.settings import SettingsInfo

settings = SettingsInfo(
    CURL_CFFI_NATIVE_DIR=Path("D:/native/my-curl-build")
)
```

生成项目在 `.env.example` 中暴露相同可选配置：

```dotenv
SCRAPY_CFFI_CURL_CFFI_NATIVE_DIR=profiles/artifacts/windows-x86_64-py312
```

`startproject`、Scheduler Demo 与 `demo -tls` 会生成 `profiles/` 参考目录；原生文件仍由用户拥有，不会复制到发行 wheel。

## 产物目录契约

目录名可以自定义，内容应符合：

```text
my-curl-build/
|-- _wrapper.<当前 Python 扩展后缀>
|-- libcurl-impersonate.dll              # Windows
|-- libcurl-impersonate.so.4             # Linux
|-- <其他相邻原生依赖>
`-- scrapy_cffi_profiles.toml             # 可选
```

只有 ABI 匹配的 `_wrapper` 有固定文件名要求。Windows 与 Linux 产物必须分目录保存，不能混入同一个运行时目录。

可选清单用于注册易读别名：

```toml
schema_version = 1

[profiles.my-browser-stable]
impersonate = "my_native_profile_v1"

[profiles.my-browser-stable.client_hints]
Sec-CH-UA-Arch = '"x86"'
Sec-CH-UA-Bitness = '"64"'
```

默认 curl 传输启用原生目录时会加载清单并注册别名。相同定义可幂等重复激活；冲突定义会直接失败，不能静默改变请求行为。没有清单时可以直接使用编译后的原生目标名。

Profile 注册应在应用启动阶段、Session 构造前完成。`SessionWrapper` 在原生实现激活后缓存解析回调，请求热路径不会重复执行功能开关或模块查询。

## 请求显式选择

```python
from scrapy_cffi.internet import HttpRequest

yield HttpRequest(
    url="https://tls.peet.ws/api/all",
    impersonate="my-browser-stable",
    callback=self.parse,
)
```

别名复用现有 `impersonate` 字段，不增加第二套 Profile 参数，因此没有优先级歧义。也可在应用启动时注册：

```python
from scrapy_cffi.profiles import register_profile

register_profile("my-browser-stable", "my_native_profile_v1")
```

未指定 `impersonate` 时不使用任何模拟 Profile。未知值会原样交给 `curl_cffi`，以兼容内置 Profile 和直接编译目标。Media、Streaming 与 WebSocket 请求使用同一解析规则，Scheduler 持久化也会保存选定值。

## 强制 Client Hints 拦截器

下载链始终安装支持 Session 的 Client Hints 拦截器。没有显式 `impersonate` 时它是无操作；对 HTTPS Profile 请求，它读取 `Accept-CH`，按 Session、Origin 与 Profile 保存偏好，并向后续请求注入已知高熵值。

请求已有 Header 优先，低熵 UA Header 仍由 `curl_cffi` 管理。缺失值可由 `Spider.resolve_client_hint` 提供。拦截器不会为了 `Critical-CH` 重放请求，也不会生成 `RESCHEDULE`，Request Manager 的 acquire/release 仍是唯一生命周期所有者。Client Hint 状态与 Cookie 一起持久化。

## 兼容性

- Python 3.9：`curl_cffi>=0.7.4,<0.14`；
- Python 3.10+：`curl_cffi>=0.7.4,<0.16`；
- 外部包装必须同时匹配当前 Python ABI 和已安装的 `curl_cffi` Python API；
- 未设置 `CURL_CFFI_NATIVE_DIR` 时，官方 `curl_cffi` 行为不变。

## TLS 检查 Demo

`scrapy-cffi demo -tls` 生成独立 Spider，请求多个 TLS 诊断 JSON 端点。`impersonate_profiles` 默认只包含 `None`；用户显式加入内置 Profile、清单别名或直接编译目标后比较指纹。

## 事件驱动 WebSocket 生命周期

长连接监听器直接把 Frame 分发给回调，并等待生命周期事件，不再把可配置结束标记塞入队列。初始 `WebSocketRequest` 仍拥有 `send_message`，并在第一次接收前发送。Spider 完成时调用 `response.stop_listening()`；Crawler 关闭和旧 `CloseSignal` 路径设置同一个停止事件。`WS_END_TAG` 只保留为兼容字段。

后续发送继续使用同一公共 `WebSocketRequest` API。带 `websocket_id` 的请求被识别为现有连接操作；如果监听器在入队后、下载前关闭，请求进入正常 `SessionEndError` 路径，不会偷偷创建替代长连接。

## 有限 Crawler 生命周期

即使多个 Spider 共用一个 TaskManager，每个 Engine 仍独立跟踪自己的生产者、Scheduler 循环、Downloader 工作、回调和监听器。有限队列 Spider 只有在生产者显式返回且自身请求计数归零后停止。

标准队列 Spider 使用 `start_request_limit`：`None` 表示持续监听，正数表示接收指定数量的入口消息后返回。空 Broker 读取和经过时间永远不会生成完成信号。Memory、Redis、RabbitMQ 与 Kafka 生成 Demo 都从 `runner.py` 验证这条路径；“休眠后强制调用 `crawler.shutdown()`”不再算成功。
