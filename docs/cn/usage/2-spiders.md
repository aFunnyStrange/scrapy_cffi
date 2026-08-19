# Spider 开发

[English](../../en/usage/2-spiders.md) | 简体中文

## 1. BaseSpider

常用类属性：

| 属性 | 默认值 | 说明 |
| --- | --- | --- |
| `name` | `cffiSpider` | Spider 唯一名称，也参与队列与去重命名空间 |
| `robot_scheme` | `https` | 生成 robots.txt URL 的协议 |
| `allowed_domains` | `[]` | 允许主机名；按 Host 匹配，不包含端口 |
| `settings_overlay` | `{}` | 当前 Spider 对基础 `SettingsInfo` 的字段覆盖 |
| `start_request_limit` | `None` | 队列入口接收上限；`None` 表示持续消费者，正数表示接收指定数量后生产者返回 |

实例获得 `settings`、`run_py_dir`、`stop_event`、`resources`、`session_id` 与 `hooks`。资源和停止事件由 Crawler 拥有，Spider 不应自行关闭它们。

### `use_execjs(ctx_key, funcname, params=())`

执行 `JS_PATH` 中已加载的 JavaScript 函数：

```python
token = self.use_execjs(
    ctx_key="crypto",
    funcname="sign",
    params=(payload, timestamp),
)
```

### `parse(response)` 与 `errRet(failure)`

`parse` 是默认响应回调，具体 Spider 必须实现。没有被拦截器处理的请求错误进入 `errRet`；自定义实现可记录上下文并产出后续请求或 `None`。

`resolve_client_hint(name, origin, response)` 可为自定义 Profile 补充缺失的高熵 Client Hint，默认返回 `None`。

## 2. Spider 类型

### 普通 `Spider`

`start_urls` 中每个 URL 会转换为带默认 Header、Cookie、Proxy、Timeout、Callback 与 Errback 的 GET `HttpRequest`。生产者遍历结束后进入有限任务收敛；只有所有自有工作完成后 Engine 才结束。

```python
from scrapy_cffi.spiders import Spider

class ExampleSpider(Spider):
    name = "example"
    allowed_domains = ["example.com"]
    start_urls = ["https://example.com/"]

    async def parse(self, response):
        yield {"title": response.css("title::text").get()}
```

### `RedisSpider`

默认从 `redis_key` 对应 Redis List 读取 URL。也可使用 Redis Stream/XGROUP：

| 属性 | 默认值 | 说明 |
| --- | --- | --- |
| `redis_key` | `redis_key` | List Key 或 Stream Key |
| `redis_start_mode` | `list` | `list` 或 `stream` |
| `redis_group` | `None` | Consumer Group；兼容 `redis_xgroup` |
| `redis_consumer` | `None` | Consumer 名，默认 Spider 名 |
| `redis_stream_field` | `data` | XADD 载荷字段 |
| `redis_stream_count` | `1` | 单次读取数量 |
| `redis_stream_block_ms` | `2000` | 单次阻塞读取边界，不是完成信号 |
| `redis_stream_ack` | `True` | 成功交付后自动确认 |

Spider 类属性优先于 `settings.REDIS_STREAM_INFO`，最后使用框架默认值。覆盖 `make_request_from_data(data: bytes)` 可解析 JSON 等自定义任务载荷。

```python
class TaskSpider(RedisSpider):
    name = "task_worker"
    redis_key = "project:tasks"
    redis_start_mode = "stream"
    redis_group = "workers"

    async def make_request_from_data(self, data: bytes):
        task = json.loads(data)
        return HttpRequest(
            url=task["url"],
            meta={"task_id": task["id"]},
            callback=self.parse,
        )
```

`start_request_limit=None` 时，暂时读取不到消息只会继续等待；空队列永远不表示完成。

### `RabbitmqSpider`

继承 `RedisSpider` 的任务转换契约，默认队列 `rabbitmq_queue="scrapy_cffi"`。RabbitMQ 携带启动和增量 Request，Redis 继续负责分布式去重和可选 Session 持久化。

### `KafkaSpider`

使用独立 Start Topic 与 Work Topic。Start 消息如果以 `SCF1` 开头，会反序列化为持久化 Request；否则交给 `make_request_from_data`。Offset 只在对应下游工作完成后连续确认，不能越过未完成的更早 Offset。

## 3. Spider 输出

异步回调可返回或 `yield`：

- `Request`：进入当前 Spider 的 Scheduler；
- `Item` 或 `dict`：进入 Pipeline；
- `None`：忽略；
- 可迭代容器：框架逐项展开；
- 异步生成器：推荐用于流式产生多个结果。

```python
async def parse(self, response):
    for href in response.css("a::attr(href)").getall():
        yield HttpRequest(url=response.urljoin(href), callback=self.parse_detail)
    yield {"source": response.url}
```

同步 `def` 回调也支持普通值、容器和 Generator，但不能在其中直接等待异步 I/O；需要 I/O 的回调应使用 `async def`。

## 4. 覆盖 `start`

自定义 `start` 是真实输入生产者。它返回只表示“不再产生启动请求”，Engine 仍需等待已调度请求、回调和监听器结束。

```python
async def start(self):
    yield HttpRequest(
        url="https://example.com/login",
        method="POST",
        data={"name": "demo"},
        callback=self.parse,
    )
```

不要通过固定休眠、重复空读或轮询次数判断生产者完成。持续输入必须等待 `stop_event` 或其他显式停止事件；有限输入应自然返回。
