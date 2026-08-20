# Self-built curl profile artifacts

`scrapy_cffi` does not bundle native profile binaries. Keep each operating
system, architecture, and Python ABI in its own runtime directory:

```text
profiles/
`-- artifacts/
    `-- windows-x86_64-py312/
        |-- _wrapper.cp312-win_amd64.pyd
        |-- libcurl-impersonate.dll
        |-- <other adjacent DLLs>
        `-- scrapy_cffi_profiles.toml
```

Linux uses its ABI-specific `_wrapper*.so` and adjacent shared libraries in a
separate directory. Copy `scrapy_cffi_profiles.example.toml` into the selected
runtime directory as `scrapy_cffi_profiles.toml`, then edit its aliases.

Point `CURL_CFFI_RUNTIME_DIR` at that exact runtime directory. The
framework loads it only when the default curl transport is constructed. Every
request must still select an alias or native target explicitly through
`impersonate`.

The manifest can optionally store high-entropy Client Hint values under a
profile's `client_hints` table. The built-in interceptor is always installed,
but remains dormant unless a request explicitly sets `impersonate` and an
HTTPS response advertises `Accept-CH`. It keeps preferences in that request's
session and origin, then adds known values to later requests without replacing
or rescheduling them. Low-entropy UA hints remain owned by curl_cffi.

If a site requests a value that cannot be declared in the artifact manifest,
override `BaseSpider.resolve_client_hint`. The callback is invoked when the
response is observed; it does not trigger an automatic retry.

Native artifacts should normally stay out of source control. The wrapper must
match the running Python ABI and the installed curl_cffi Python API.
