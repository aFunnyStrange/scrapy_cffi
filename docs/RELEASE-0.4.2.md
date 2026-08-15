# Draft for scrapy_cffi 0.4.2: self-built curl profiles

This unreleased draft documents the self-built profile support planned for
scrapy_cffi 0.4.2. It integrates the request-profile adapter that was previously
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
SCRAPY_CFFI_CURL_CFFI_NATIVE_DIR=D:/native/my-curl-build
```

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

[profiles]
my-browser-stable = "my_native_profile_v1"
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

## Compatibility

- Python 3.9 keeps the existing `curl_cffi>=0.7.4,<0.14` dependency contract.
- Python 3.10+ keeps `curl_cffi>=0.7.4,<0.16`.
- External wrappers must match both the running Python ABI and the installed
  curl_cffi Python API.
- Without `CURL_CFFI_NATIVE_DIR`, the official installed curl_cffi behavior is
  unchanged.
