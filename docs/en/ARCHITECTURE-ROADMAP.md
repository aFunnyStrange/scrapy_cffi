# Architecture roadmap

`scrapy_cffi` is a lightweight asynchronous Worker kernel. Crawler is its first
and currently most complete specialized Worker adapter; generic resource,
thread, subprocess, and server capabilities remain independently composable.

## Current 0.4 layer model

```text
runner
  -> Crawler composition root
  -> core services / schedulers / spiders / pipelines
  -> runtime (generic shared-resource lifecycle and worker context)
  -> service (bounded resilience)
  -> repo (storage and request-queue semantics)
  -> infra (one-shot external-system clients)
  -> platform (reusable HTTP and codec capabilities)
```

Concrete infrastructure is parallel by external system:

```text
infra/redis
infra/rabbitmq
infra/kafka
infra/sqlalchemy
infra/mongodb
```

Redis is not placed under a database-only or broker-only category because it can provide deduplication, session state, lists, Streams, coordination, and cache capabilities.

## Completed

- [x] Framework-owned HTTP/WebSocket/stream Protocols and curl_cffi adapter.
- [x] `config` owns Pydantic connection and topology models.
- [x] `infra` clients contain no crawler state, retry loop, or reconnect controller.
- [x] `repo` owns Redis dedup/session/queue semantics, SQL/Mongo operations, and transport-neutral request queues.
- [x] `service.ResourceService` owns lifecycle; `RetryPolicy` and `ResourceSlot` provide bounded replacement.
- [x] `composition.build_resource_service` is shared by Crawler, direct use, and functional tests.
- [x] Schedulers consume Protocols instead of concrete Redis/RabbitMQ/Kafka clients.
- [x] Pipelines, spiders, and extensions receive one typed resource service.
- [x] Application `Resource` classes are loaded from `RESOURCES_PATH`, started
      in order, injected globally, and closed in reverse order.
- [x] Old `databases`, `mq`, and `utils.reconnect` implementation modules removed.
- [x] Typed lazy exports retain optional-dependency isolation and IDE navigation.
- [x] Memory, Redis, RabbitMQ, Kafka, persistence, Ctrl+C cleanup, stream, and SSE flows covered by tests.

## Dependency rules

- Lower layers never import crawler, scheduler, pipeline, or service modules.
- Infra performs one operation once and propagates vendor failures.
- Repository methods define replayable boundaries; native client escape hatches remain explicitly one-shot.
- Service retry is bounded, cancellation-aware, observable, and replaces one failed generation only once under concurrency.
- Composition is the only place that selects concrete external-system implementations.

## Future work

- Add only project-specific object-storage adapters through `Resource`; keep
  vendor credentials and non-uniform APIs outside the framework core.
- Introduce generic run scopes only after a second non-crawler Worker needs the
  same lifecycle; Crawler remains the currently specialized Worker adapter.
- Add database-backed authoritative task state only when a workflow needs cross-stage business status beyond scheduler persistence.
