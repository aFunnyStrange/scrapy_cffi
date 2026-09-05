# scrapy_cffi 0.4.4: a lightweight asynchronous Worker kernel

[English](../en/RELEASE-0.4.4.md) | [简体中文](../cn/RELEASE-0.4.4.md)

Version 0.4.4 develops scrapy_cffi toward a reusable asynchronous Worker
kernel while preserving its specialized crawler runtime. The framework still
runs one asyncio event loop by default and does not silently introduce threads,
processes, a durable scheduler, or a Celery dependency.

## Short media and process work

Media helpers cover image, video, and audio metadata through optional,
cross-platform libraries. Blocking Pillow and hachoir operations have explicit
`asyncio.to_thread()` facades.

`FFmpegProcessManager` starts shell-free subprocesses with
`asyncio.create_subprocess_exec()`, bounds live processes, records explicit
states, retains bounded output tails, and supports graceful stop followed by
terminate/kill. Short awaited jobs may run inside a Spider. Long-running pulls
remain owned by the application `runner.py`; the crawler neither restarts nor
supervises them.

The crawler-owned `ProcessTaskManager` is also lazy and bounded. It is intended
only for short, picklable CPU work. Multiprocess scheduling remains an
application concern.

## Application-owned resources

Projects can register `Resource` classes in settings. The runtime creates one
shared instance, starts resources in dependency order, and closes them in
reverse order. Spiders, pipelines, interceptors, extensions, and signal hooks
receive the same registry.

The framework supplies lifecycle and typed lookup, not a pretend universal BOS
or vendor SDK. Users retain ownership of credentials, client construction, and
provider-specific methods. Pipeline `open_spider()` and `close_spider()` remain
useful for per-Spider state but no longer own shared infrastructure.

## Runs, status, and the optional Hub

`RunContext` identifies a process instance, invocation, optional durable task,
and attempt. `start_spider_run()` and `start_all_spiders_run()` return a
`CrawlerRunHandle` that can be awaited or explicitly stopped while existing
runner APIs remain compatible.

The opt-in monitoring extension reports lifecycle, heartbeat, counters, and
errors. The experimental FastAPI Hub keeps bounded observation state and may
read application tasks through a user-provided `TaskStateProvider`; it never
writes or replaces the MySQL/Postgres task source of truth. A stale heartbeat
changes availability to `unreachable` but cannot invent a completed or failed
run.

The optional email extension similarly stays outside the hot path. It opens
SMTP lazily, sends aggregated completion summaries, and can send immediate
errors only when configured.

## HTTP/3 boundary

`HttpVersion.HTTP_3` and `HTTP_3_ONLY` expose the request preference supported
by qualified curl_cffi/libcurl builds. This is not a general QUIC stream,
datagram, Server Push, callback-listener, WebTransport, or proxy-control API.
The optional aioquic Demo server documents and tests the current experimental
request-only boundary.

## Generated projects and compatibility

Normal projects and Demos both receive `project_support/` topology helpers.
Generated `runner.py` includes a `managed_main()` example for mapping a
framework run outcome into application-owned durable task transitions.

The release retains Python 3.9 support, lazy optional imports, finite natural
completion, and explicit shutdown for continuous Redis, RabbitMQ, and Kafka
Spiders. The full generated-project matrix is validated on Windows and WSL
Ubuntu before the release tag is created.
