# Item pipelines

Pipelines retain Scrapy-style async lifecycle hooks while receiving framework services through stable contracts.

## Attributes

| Attribute | Description |
| --- | --- |
| `settings` | Validated `SettingsInfo` for the crawler. |
| `logger` | Framework logger. |
| `resources` | Typed `ResourceService` with optional `redis`, `mysql`, `postgres`, `mongodb`, `rabbitmq`, and `kafka` repositories. |
| `hooks` | Pipeline-facing session and signal hooks. |

The old six `*Manager` attributes were removed in 0.4. Repositories expose stable persistence and queue semantics; client lifecycle, bounded retry, and replacement are centralized in `ResourceService`.

```python
from scrapy_cffi.pipelines import Pipeline


class SavePipeline(Pipeline):
    async def process_item(self, item, spider):
        postgres = self.resources.postgres
        if postgres is None:
            raise RuntimeError("POSTGRES_INFO is not configured")
        await postgres.execute(
            "insert into items(name) values (:name)",
            {"name": item["name"]},
        )
        return item
```

Use `repository.client`, `engine`, or `session_factory` only when native vendor operations are intentional. Those escape-hatch calls are one-shot and are not silently replayed.

## Lifecycle

### `open_spider(spider)`

Called when the spider opens. Infrastructure has already been started, so use this hook for pipeline-specific preparation.

### `process_item(item, spider)`

Receives every item yielded by callbacks and may validate, transform, persist, or drop it.

### `close_spider(spider)`

Called when the spider closes. Shared infrastructure is closed centrally after all engines stop; do not close `self.resources` from an individual pipeline.

When `run_all_spiders` hosts multiple spiders in one crawler, they share one resource service and close together after all scheduled work completes.
