# Custom runtime resources

[简体中文](../../cn/usage/16-custom-resources.md) | English

`scrapy_cffi.runtime.Resource` is the extension point for application-owned
infrastructure and shared capabilities that do not fit the built-in database
or message-queue repositories. A resource may wrap object storage, a local
artifact store, a vendor SDK, or another runtime-scoped client. The framework
does not normalize vendor credentials or methods.

## Define and register a resource

```python
from scrapy_cffi import Resource


class BosResource(Resource):
    name = "bos"

    async def start(self):
        # Import the optional vendor SDK here and construct the client with
        # application-owned configuration. Use asyncio.to_thread when the SDK
        # performs blocking I/O.
        self.client = await create_project_bos_client(self.settings)

    async def put(self, key, data):
        return await self.client.put(key, data)

    async def close(self):
        await self.client.close()
```

Register classes in dependency order:

```python
settings.RESOURCES_PATH = [BosResource]

# Dotted paths are also supported for configuration-driven projects.
# settings.RESOURCES_PATH = ["project.resources.BosResource"]
```

The runtime constructs one instance, calls `start()` before creating worker
components, and calls `close()` in reverse registration order during shutdown.
Late and duplicate registration fail before user work starts.

## Consume the shared resource

Spider, Pipeline, Interceptor, and Extension instances receive the same
registry:

```python
bos = self.resources.require("bos")
await bos.put("responses/1.json", body)

# Attribute syntax is available for concise application code.
await self.resources.bos.put("responses/2.json", body)
```

Use `require()` where an absent resource is a configuration error and `get()`
where it is genuinely optional. Large payloads should be stored first; queues
should carry bounded keys or artifact references.

For IDE completion and static type checking, pass the expected Resource class:

```python
bos = self.resources.require_typed("bos", BosResource)
await bos.put("responses/3.json", body)  # BosResource methods are discoverable.

optional_bos = self.resources.get_typed("bos", BosResource)
if optional_bos is not None:
    await optional_bos.put("responses/4.json", body)
```

`get_typed()` returns `None` when the resource is absent. Both typed methods
raise `TypeError` when a name resolves to a different class, preventing a type
hint from concealing an invalid runtime configuration.

## Resource versus Extension

Both are loaded from settings, but their contracts differ:

- A Resource owns a shared dependency and its runtime-level `start/close`.
- An Extension observes signals and adds behavior to crawler execution.
- A Pipeline processes items and receives per-Spider lifecycle notifications.

`open_spider()` and `close_spider()` must not open or close shared resources.
They remain useful for per-Spider buffers, validation, metrics, manifests, and
final flushes. Because Pipeline instances may be shared by concurrent Engines,
such state must be keyed by Spider or run identity.
