# scrapy_cffi 0.4.0

Version 0.4 establishes stable platform and external-resource boundaries while adding incremental HTTP/SSE responses.

## HTTP platform

Crawler sessions and the downloader consume framework-owned async Protocols. `CurlCffiHttpSession` is the default adapter and isolates curl_cffi 0.7.4 through 0.15 API differences.

- Python 3.9 installs `curl_cffi>=0.7.4,<0.14`.
- Python 3.10+ installs `curl_cffi>=0.7.4,<0.16`.
- `HTTP_SESSION_FACTORY` accepts another protocol-compatible transport.
- Framework `WebSocketFlag` values are converted at the adapter boundary.

## Streaming and SSE

`HttpRequest(stream=True)` returns `StreamResponse` with `aiter_bytes`, `aiter_lines`, `aiter_sse`, and idempotent `aclose`. Live streams own bounded downloader capacity and close after callback completion, replacement, cancellation, or shutdown. SSE event buffering is bounded to 1 MiB by default.

## External-resource architecture

Database and request-queue code now follows:

```text
Crawler / Pipeline / Spider
  -> ResourceService
  -> repository Protocol and implementation
  -> one-shot infra client
  -> vendor driver
```

Infrastructure is parallel by concrete system: `infra/redis`, `rabbitmq`, `kafka`, `sqlalchemy`, and `mongodb`. There is no `infra/broker` category because Redis lists and Streams can also carry work.

`ResourceSlot` owns one replaceable client generation. `RetryPolicy` performs bounded, cancellation-aware recovery above repositories, collapses concurrent failures from the same generation, and logs retries when a crawler logger is available. Infra clients contain no crawler stop event, retry decorator, or reconnect controller.

Schedulers consume `RedisRepositoryProtocol` and `RequestQueueRepositoryProtocol`. Pipelines, spiders, and extensions receive a typed `resources` service. Direct functional tests use the same `build_resource_service(settings, stop_event)` composition path.

## Breaking cleanup

The old `scrapy_cffi.databases`, `scrapy_cffi.mq`, `utils.reconnect`, and six concrete `*Manager` attributes were removed. Connection/topology models moved from generic `models` into `scrapy_cffi.config`. RabbitMQ and Kafka share the queue-semantic `QueueConnectionInfo` / `QueueTopology` names without imposing an `infra/broker` hierarchy on Redis or any concrete system.

The supported public paths are now:

- `scrapy_cffi.config` for Pydantic settings models;
- `scrapy_cffi.infra.<system>` for deliberate one-shot driver access;
- `scrapy_cffi.repo` for stable persistence and queue semantics;
- `scrapy_cffi.service` for lifecycle/resilience extensions;
- `scrapy_cffi.build_resource_service` for normal direct use and tests.

## IDE and verification

Typed lazy exports expose real definitions to static analyzers while optional drivers remain isolated. The release suite covers memory, Redis, RabbitMQ, Kafka, Cookie persistence, non-persistent cleanup, Ctrl+C recovery, HTTP/WebSocket, stream/SSE, Python 3.9 compatibility, and multiple curl_cffi versions.
