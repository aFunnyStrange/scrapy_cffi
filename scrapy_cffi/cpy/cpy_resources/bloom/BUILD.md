# Bloom ctypes module (no prebuilt binaries in the package)

The framework ships **Python only** here: `wrapper.py`, `fallback.py`, `bloom.pyi`.
Native libraries are **not** published with PyPI — build for your OS/Python and install globally or per-project.

## Quick start

```bash
# 1. Already included when you run scrapy-cffi startproject (optional re-scaffold)
scrapy-cffi cinstall --init bloom

# 2. Build from C sources (see tests/c_bloom/readme.md in the repo)
#    Output: build/libbloom.dll | libbloom.so | libbloom.dylib

# 3. Install to system store (all projects on this machine)
scrapy-cffi cinstall bloom --source ./cpy_resources/bloom --require-binary

# Or only for this project: keep build/ under ./cpy_resources/bloom/
```

## Load order at runtime

1. Project `./cpy_resources/bloom/` (if configured)
2. System store (`scrapy-cffi cinstall --path`)
3. Framework package (fallback.py if no native lib)

Override system path: `SCRAPY_CFFI_CPY_DIR`.

See [docs/usage/12-cpython.md](../../../../docs/usage/12-cpython.md).
