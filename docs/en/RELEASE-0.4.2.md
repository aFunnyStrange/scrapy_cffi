# scrapy_cffi 0.4.2: self-built curl profiles

This release documents the self-built profile support added in scrapy_cffi
0.4.2. It integrates the request-profile adapter that was previously
a separate local package. A compatible self-built `curl-impersonate` wrapper
can be selected by the framework while every request still chooses its own
profile explicitly.

## Runtime boundary

`CURL_CFFI_NATIVE_DIR` selects the process-level native implementation. The
directory must contain an `_wrapper` matching the running Python ABI and its
adjacent Windows DLL or Linux shared-library dependencies. This is not a
default impersonation setting.

The adapter is runtime-only: native binaries and concrete profile definitions
are not bundled into the
`scrapy_cffi` wheel and are not build-time dependencies. Leaving the setting
unset does not activate the adapter and preserves the official installed
`curl_cffi` implementation.

```python
from pathlib import Path

from scrapy_cffi.settings import SettingsInfo


settings = SettingsInfo(
    CURL_CFFI_NATIVE_DIR=Path("D:/native/my-curl-build")
)
```

Generated projects expose the same optional setting in `.env.example`:

```dotenv
SCRAPY_CFFI_CURL_CFFI_NATIVE_DIR=profiles/artifacts/windows-x86_64-py312
```

`scrapy-cffi startproject`, the scheduler demos, and `scrapy-cffi demo -tls`
generate a `profiles/` reference directory. Native files remain user-owned and
are not copied into the published wheel.

## Artifact directory contract

Users can choose any directory name. Its contents follow this portable shape:

```text
my-curl-build/
|-- _wrapper.<running-python-extension-suffix>
|-- libcurl-impersonate.dll              # Windows
|-- libcurl-impersonate.so.4             # Linux alternative
|-- <other adjacent native dependencies>
`-- scrapy_cffi_profiles.toml             # optional
```

Only the ABI-matching `_wrapper` is mandatory by filename contract. Its native
libraries must be loadable from the same directory and must come from a
compatible build. Windows and Linux artifacts should be placed in separate
directories rather than mixed into one runtime directory.

The optional manifest is the user-friendly alias registration contract:

```toml
schema_version = 1

[profiles.my-browser-stable]
impersonate = "my_native_profile_v1"

[profiles.my-browser-stable.client_hints]
Sec-CH-UA-Arch = '"x86"'
Sec-CH-UA-Bitness = '"64"'
```

When the default curl transport activates `CURL_CFFI_NATIVE_DIR`, it loads this
manifest and registers each alias. Repeated activation of the same definitions
is idempotent; conflicting definitions fail instead of silently changing
request behavior. Without a manifest, callers may use compiled native target
names directly.

The registry selects an `impersonate` resolver callback during startup. Before
any custom alias is registered, the callback is a zero-lookup passthrough to
curl_cffi. Manifest or programmatic registration switches it to the alias
resolver. Each `SessionWrapper` caches the selected callback after native
activation, so request construction performs no feature-flag branch or module
lookup in the hot path. Programmatic registration should therefore happen
during application startup, before sessions are constructed.

## Explicit request selection

Use an alias declared by the user's artifact manifest:

```python
from scrapy_cffi.internet import HttpRequest


yield HttpRequest(
    url="https://tls.peet.ws/api/all",
    impersonate="my-browser-stable",
    callback=self.parse,
)
```

Registered aliases use the existing `impersonate` field. The framework does
not add a second profile-selection argument, so there is no field priority or
ambiguity; selection remains request-scoped.

Aliases can also be registered in application startup code:

```python
from scrapy_cffi.profiles import register_profile


register_profile("my-browser-stable", "my_native_profile_v1")
```

Or pass a native/vendor target directly:

```python
yield HttpRequest(
    url="https://example.com",
    impersonate="vendor-profile",
    callback=self.parse,
)
```

Passing neither option uses no impersonation profile. Unknown values pass
through unchanged to preserve curl_cffi built-in profiles and direct compiled
targets. The same resolution applies to media, streaming, and WebSocket
requests, and the selected value survives scheduler persistence.

## Mandatory Client Hints interceptor

The download chain always installs a session-aware Client Hints interceptor.
It remains a no-op for requests without an explicit `impersonate`. For HTTPS
profiled requests it observes `Accept-CH`, stores the origin preference in the
same session, and injects known high-entropy values into later requests for the
same origin and profile. Existing request headers have priority, and curl_cffi
continues to own the low-entropy UA headers it emits for impersonation.

Missing values may be supplied by `Spider.resolve_client_hint`. The
interceptor deliberately does not replay `Critical-CH` responses: it returns
the original response and never creates a `RESCHEDULE` result, so the request
manager's existing acquire/release pair remains the sole lifecycle owner.
Client Hint session state is persisted together with cookies.

## Compatibility

- Python 3.9 keeps the existing `curl_cffi>=0.7.4,<0.14` dependency contract.
- Python 3.10+ keeps `curl_cffi>=0.7.4,<0.16`.
- External wrappers must match both the running Python ABI and the installed
  curl_cffi Python API.
- Without `CURL_CFFI_NATIVE_DIR`, the official installed curl_cffi behavior is
  unchanged.

## TLS inspection demo

`scrapy-cffi demo -tls` generates a standalone spider that calls several TLS
diagnostic JSON endpoints. Its `impersonate_profiles` tuple is intentionally
empty-by-default (`None` only): users add curl_cffi built-ins, manifest aliases,
or direct compiled targets explicitly and compare the returned fingerprints.

## Event-driven WebSocket lifecycle

Long-lived WebSocket listeners dispatch frames directly to callbacks and wait
on lifecycle events rather than passing a configurable end marker through a
queue. The connecting `WebSocketRequest` still owns its initial `send_message`,
which is sent before the first receive operation. Call
`response.stop_listening()` when the spider is done. Crawler shutdown and the
legacy `CloseSignal` path set the same stop event; `WS_END_TAG` remains only as
a deprecated settings compatibility field.

Follow-up sends retain the same public `WebSocketRequest` API. Internally, a
request with `websocket_id` is classified as an existing-connection operation.
If the listener closes after enqueue but before download, the request follows
the normal `SessionEndError` path instead of silently opening a replacement
long-lived connection.

## Finite crawler lifecycle

Each Engine tracks its own producer, scheduler loops, downloader work,
callbacks, and listeners even when several spiders share one TaskManager. A
finite queue-backed spider stops after its producer explicitly returns and its
owned request count reaches zero. Standard queue Spiders expose
`start_request_limit`: `None` listens continuously, while a positive value
returns after that many accepted ingress messages. Empty broker reads and
elapsed time never produce a completion signal.
The generated Memory, Redis, RabbitMQ, and Kafka demos exercise this path from
`runner.py`; verification no longer treats a timed sleep followed by forced
`crawler.shutdown()` as success.
