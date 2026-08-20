# scrapy_cffi 0.4.3: explicit runtime and resource boundaries

[English](../en/RELEASE-0.4.3.md) | [简体中文](../cn/RELEASE-0.4.3.md)

Version 0.4.3 makes concurrency, session state, native activation, and user
resource ownership explicit without changing the established global safety
default.

## Concurrency and session limits

The three controls have independent meanings:

- `MAX_GLOBAL_CONCURRENT_TASKS=300` bounds all managed work in one Engine.
- `MAX_CONCURRENT_REQ=None` adds no downloader-local concurrency limit.
- `SESSION_REQUESTS_PER_SECOND=None` adds no per-session request-start rate.

Applications can set a global per-session rate or configure individual
sessions through `hooks.session`. Explicit `None` always means unlimited.

## Timeout delivery

Request timeouts now produce framework-owned typed failures and reach the
request errback. A request may override its retry count and retry delay, so a
Spider can implement user-level tracing and recovery without replacing the
Downloader.

## Native runtime versus impersonation

`scrapy_cffi.platform.curl_native` owns process-level activation of an
ABI-compatible curl wrapper. `CURL_CFFI_RUNTIME_DIR` selects that runtime;
`CURL_CFFI_NATIVE_DIR` remains accepted for compatibility.

The existing request `impersonate` field remains the only profile-selection
API. Activating a native runtime does not select a browser identity for every
request.

## Resources and durable state

Spiders, pipelines, interceptors, extensions, and signal hooks all receive the
same resource service and can use configured SQL, MongoDB, Redis, RabbitMQ, or
Kafka capabilities. Pipelines are no longer treated as the only component that
may own data access.

Redis scheduler persistence stores task state by default. Persisting cookies
and client hints requires explicit opt-in. Account and device records should be
loaded from a durable database while queue messages carry lightweight task and
session references.

## Configuration and CLI

`.env` and process-environment settings accept natural Pydantic field names,
including nested names such as `REDIS_INFO__URL`; the historical
`SCRAPY_CFFI_` prefix remains compatible.

The colored banner is intentionally limited to root `scrapy-cffi -h` and
`scrapy-cffi banner`. Subcommand help stays compact.

FFmpeg multiprocessing is not part of this release and remains deferred.
