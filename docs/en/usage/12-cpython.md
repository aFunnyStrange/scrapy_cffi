# 1.Introduction
The `CPY_EXTENSIONS`/`cinstall` path is a legacy compatibility boundary for
application-owned ctypes libraries. It is not the curl impersonation runtime
and must not select TLS/browser profiles. New distributable native features
should normally use standard wheels and optional extras; curl runtime activation
belongs to `scrapy_cffi.platform` through `CURL_CFFI_RUNTIME_DIR`, while
request-scoped `impersonate` remains a profile choice.

**Loading order** (per module directory):

```text
Project cpy_resources/<module>  →  System cpy store  →  Framework cpy/cpy_resources/<module>
```

Within each directory: `wrapper.py` (ctypes) first, then `fallback.py` if the native library is missing.

**System cpy store** — install user-built binaries once for all projects.
Bloom filtering no longer uses this legacy path; install
`scrapy_cffi[bloom]` for the maintained Rust accelerator instead:

```bash
scrapy-cffi cinstall --init custom_native
scrapy-cffi cinstall custom_native --require-binary
scrapy-cffi cinstall --list
scrapy-cffi cinstall --path                  # e.g. ~/.local/share/scrapy_cffi/cpy_resources
```

Override location: `SCRAPY_CFFI_CPY_DIR`. This loader remains for explicitly
configured custom ctypes integrations and is not part of the framework Bloom
runtime.

On Windows, C extensions can also be compiled as `.pyd` files. However, `.pyd` is tightly bound to both the OS and the Python version, and requires `#include <Python.h>` in the C source. This makes cross-platform C code more difficult to maintain. Moreover, `.pyd` files can be imported directly in Python without additional configuration, but for consistency and cross-platform support, the framework standardizes all C extension loading via **ctypes**.

# 2.Recommended File Structure
A typical project structure for C extensions is:
```bash
/project
|
|- cpy_resources
|    |- module1_dir
|    |     |- build_dir
|    |     |     |- libmodule1.dll      # Windows C extension binary
|    |     |     |- libmodule1.so       # Linux C extension binary
|    |     |     |- libmodule1.dylib    # macOS C extension binary
|    |     |
|    |     |- module1.pyi               # Optional, provides static typing for IDEs
|    |     |- fallback.py               # Pure Python fallback implementation (API compatible)
|    |     |- wrapper.py                # Python wrapper that loads the C extension via ctypes
|    |
|    |- module2_dir
|    |- ...
|
|- extensions
|- interceptors
|- items
|- pipelines
|- spiders
|- settings.py
|- runner.py
```

**Notes**:
- In `SettingsInfo.CPY_EXTENSIONS`, `DIR` is a custom name for `"cpy_resources"`. It only affects user configuration and does not change internal framework paths.
- `RESOURCES` is a list of multiple `CPYExtension` resources.
- Each resource configuration is described in section 3 below.

---

# 3.CPYExtension
## 3.1 module_name
- **Type**: str 
- **Required**: yes
- **Description**: The folder name under your configured `cpy_resources` directory that contains the extension files (for example: `cpy_resources/module1_dir`). The loader locates this directory to find the wrapper/fallback files and compiled binaries.
- **Notes**:
    - **Path binding**: `module_name` is used to build filesystem paths (e.g. cpy_resources/<module_name>/wrapper.py).
    - **Must exist**: the loader will attempt to load from the directory named by `module_name` (first user-level, then framework-level).

--- 

## 3.2 resource_name
- **Type**: Optional[str]
- **Default**: None
- **Description**: The import name injected into the running process after loading. If provided, the loaded module is made available as `import <resource_name>`. If omitted, the loader uses `module_name` as the import name.
- **Notes & best practices**:
    - **Controls the runtime import name, not the filesystem name**. This lets you keep physical folder names separate from the API you expose to the application.
    - **Valid identifier**: `resource_name` should be a valid Python import identifier (letters, digits, underscores; not starting with a digit).
    - **Collision risk**: If `resource_name` conflicts with an existing module in `sys.modules`, it will overwrite that entry. Avoid names that shadow standard libraries or commonly used packages.
    - **Default injection**: The framework automatically injects the module into `sys.modules` and `globals()` so it is globally importable under `resource_name`.

---

## 3.3 wrapper
- **Type**: Optional[str]
- **Default**: "wrapper.py"
- **Description**: Python wrapper filename that handles C extension loading via ctypes.

---

## 3.4 fallback
- **Type**: Optional[str]
- **Default**: "fallback.py"
- **Description**: Pure Python fallback implementation used if the C extension fails to load. Must provide the same API.

---

## 3.5 build_dir
- **Type**: Optional[str]
- **Default**: "build"
- **Description**: Directory containing compiled shared libraries (ctypes wrapper). Matches the folder containing `.dll`, `.so`, or `.dylib`.

# 4.Examples
1. Use the same name for folder and import:
```python 
CPYExtension(module_name="custom_native")
# Directory: cpy_resources/custom_native/
# After load: import custom_native
```

2. Use a different public API name:
```python
CPYExtension(module_name="custom_impl_v1", resource_name="custom_native")
# Directory: cpy_resources/custom_impl_v1/
# After load: import custom_native
```
