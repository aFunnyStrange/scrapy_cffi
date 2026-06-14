# C Bloom filter (`tests/c_bloom`)

Due to potential differences in `Python.h` across different Python versions, for cross-platform compatibility it is generally recommended to compile shared libraries (`.dll` / `.pyd` / `.so`) and interface with them using `ctypes` or `cffi`, rather than directly relying on `Python.h`.

The framework ships a Python fallback Bloom filter; the C sources here are for optional native builds and benchmarks.

See also: [`tests/readme.md`](../readme.md) · Bloom settings `BLOOM_INFO` in [`docs/usage/1-settings.md`](../../docs/usage/1-settings.md).
