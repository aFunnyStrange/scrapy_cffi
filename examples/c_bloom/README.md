# C Bloom filter (`examples/c_bloom`)

Reference C sources for the optional `bloom` ctypes module shipped under `scrapy_cffi/cpy/cpy_resources/bloom/`.

The PyPI package does **not** include prebuilt `.dll` / `.so` / `.dylib` files. Build locally, then install:

```bash
# Scaffold module layout into your project
scrapy-cffi cinstall --init bloom

# After compiling into cpy_resources/bloom/build/libbloom.*
scrapy-cffi cinstall bloom --require-binary
```

System store path: `scrapy-cffi cinstall --path` (override with `SCRAPY_CFFI_CPY_DIR`).

See also: [`scrapy_cffi/cpy/cpy_resources/bloom/BUILD.md`](../../scrapy_cffi/cpy/cpy_resources/bloom/BUILD.md) · [`docs/usage/12-cpython.md`](../../docs/usage/12-cpython.md).

Due to potential differences in `Python.h` across Python versions, cross-platform builds use **shared libraries + ctypes** (not `.pyd` / `Python.h` bindings).

The framework always provides `fallback.py` (pure Python Bloom) when no native library is present.
