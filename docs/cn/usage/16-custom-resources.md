# 自定义 Runtime 资源

[English](../../en/usage/16-custom-resources.md) | 简体中文

`scrapy_cffi.runtime.Resource` 用于注册不属于内置数据库、MQ Repository
的应用基础设施和共享能力，例如对象存储、本地产物存储、厂商 SDK 或其他
Runtime 级客户端。框架不统一厂商账号配置，也不尝试统一厂商原生 API。

## 定义和注册资源

```python
from scrapy_cffi import Resource


class BosResource(Resource):
    name = "bos"

    async def start(self):
        # 在这里按需导入厂商 SDK，并使用项目自己的配置创建客户端。
        # 如果 SDK 执行阻塞 I/O，应使用 asyncio.to_thread 包装。
        self.client = await create_project_bos_client(self.settings)

    async def put(self, key, data):
        return await self.client.put(key, data)

    async def close(self):
        await self.client.close()
```

按照依赖顺序注册 Resource 类：

```python
settings.RESOURCES_PATH = [BosResource]

# 配置驱动的项目也可以使用点分导入路径。
# settings.RESOURCES_PATH = ["project.resources.BosResource"]
```

Runtime 只创建一个实例，在 Worker 组件创建前调用 `start()`，关闭时按照
注册顺序反向调用 `close()`。重复注册和启动后的延迟注册都会立即失败。

## 使用共享资源

Spider、Pipeline、Interceptor 和 Extension 获得同一个资源注册中心：

```python
bos = self.resources.require("bos")
await bos.put("responses/1.json", body)

# 也支持更简洁的属性访问。
await self.resources.bos.put("responses/2.json", body)
```

资源缺失属于配置错误时使用 `require()`；资源确实可选时使用 `get()`。大体积
数据应先写入对象存储，MQ 中只传递有界的 key 或产物引用。

需要 IDE 自动补全和静态类型检查时，传入期望的 Resource 类：

```python
bos = self.resources.require_typed("bos", BosResource)
await bos.put("responses/3.json", body)  # IDE 可以识别 BosResource 方法。

optional_bos = self.resources.get_typed("bos", BosResource)
if optional_bos is not None:
    await optional_bos.put("responses/4.json", body)
```

`get_typed()` 在资源不存在时返回 `None`。如果名称对应的是其他类型，两个 typed
方法都会抛出 `TypeError`，避免错误配置被类型标注掩盖。

## Resource 与 Extension 的区别

两者都会从 settings 加载，但职责不同：

- Resource 持有共享依赖及其 Runtime 级 `start/close` 生命周期。
- Extension 订阅信号，为爬虫执行增加行为。
- Pipeline 处理 Item，并接收每个 Spider 的生命周期通知。

`open_spider()` 和 `close_spider()` 不得创建或关闭共享资源。它们仍适合
管理单个 Spider 的缓冲、配置校验、指标、结果清单和最终 flush。多个 Engine
可能共享同一个 Pipeline 实例，因此这些状态必须按照 Spider 或 run 标识隔离。
