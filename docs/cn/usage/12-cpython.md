# 1. CPython / ctypes 扩展

[English](../../en/usage/12-cpython.md) | 简体中文

框架按 `SettingsInfo.CPY_EXTENSIONS` 加载自定义 C 扩展。每个模块目录的搜索顺序为：

```text
项目 cpy_resources/<module>
  -> 用户系统 cpy store
  -> 框架 cpy/cpy_resources/<module>
```

每个目录先加载 `wrapper.py`（ctypes）；原生库缺失时加载 `fallback.py`。Bloom 已迁移到维护中的 Rust 加速 extra `scrapy_cffi[bloom]`，不再走这条旧路径。

```bash
scrapy-cffi cinstall --init custom_native
scrapy-cffi cinstall custom_native --require-binary
scrapy-cffi cinstall --list
scrapy-cffi cinstall --path
```

`SCRAPY_CFFI_CPY_DIR` 可覆盖系统存储目录。虽然 Windows 可以生成 `.pyd`，它与 OS 和 Python ABI 强绑定；本框架为跨平台一致性统一使用 ctypes 包装。

# 2. 推荐目录

```text
project/
├─ cpy_resources/
│  └─ module1_dir/
│     ├─ build/
│     │  ├─ libmodule1.dll
│     │  ├─ libmodule1.so
│     │  └─ libmodule1.dylib
│     ├─ module1.pyi
│     ├─ fallback.py
│     └─ wrapper.py
├─ spiders/
├─ settings.py
└─ runner.py
```

# 3. `CPYExtension`

- `module_name: str`：必填，`cpy_resources` 下实际目录名，也是默认导入名。
- `resource_name: Optional[str]`：运行时导入名；为空时使用 `module_name`。必须是合法 Python 标识符，不能覆盖标准库或常用包。
- `wrapper: str = "wrapper.py"`：ctypes 包装文件。
- `fallback: str = "fallback.py"`：原生库不可用时的纯 Python 等价实现。
- `build_dir: str = "build"`：`.dll`、`.so`、`.dylib` 所在目录。

```python
CPYExtension(module_name="custom_native")
# import custom_native

CPYExtension(
    module_name="custom_impl_v1",
    resource_name="custom_native",
)
# 目录仍是 custom_impl_v1，公共导入名为 custom_native
```

