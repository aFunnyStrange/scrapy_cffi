"""
Lazy export registry for ``scrapy_cffi.utils``.

Prefer explicit submodule imports (lighter, clearer):

    from scrapy_cffi.utils.algorithm import do_sha1
    from scrapy_cffi.utils.media import guess_content_type

Barrel access ``from scrapy_cffi.utils import do_sha1`` remains supported via ``__getattr__``.
"""

from __future__ import annotations

from importlib import import_module
from typing import Dict, Tuple

_UTILS_PKG = "scrapy_cffi.utils"

_EXPORTS: Dict[str, str] = {}

def _reg(mod: str, *names: str) -> None:
    for name in names:
        _EXPORTS[name] = mod


_reg("algorithm", "do_sha1", "create_uniqueId", "do_otp", "get_node")
_reg(
    "common",
    "get_run_py_dir",
    "get_or_create_loop",
    "setup_uvloop_once",
    "async_context_factory",
    "ResultHolder",
    "load_object",
    "to_scrapy_settings_py",
    "load_settings_with_path",
    "load_settings_from_py",
    "convert_to_toml",
    "get_class_name",
    "get_all_spiders_cls",
    "get_all_spiders_name",
    "run_with_timeout",
)
_reg(
    "concurrency",
    "run_coroutine_in_new_loop",
    "run_coroutine_in_thread",
    "ProcessTaskManager",
    "ProcessManager",
    "ThreadFuture",
    "CallFunction",
    "safe_call",
)
_reg(
    "jsonLoad",
    "extract_nested_objects",
    "JSONExtractor",
    "JSONScanner",
    "extract_json_chain",
)
_reg("protobuf", "ProtobufFactory")
_reg("email", "Email")
_reg(
    "log",
    "ShortNameFormatter",
    "init_logger",
    "start_multiprocess_log_listener",
    "init_logger_multiprocessing",
    "KafkaLoggingHandler",
)
_reg("robot", "RobotsTxtRules", "parse_robots_txt", "RobotsManager")
_reg(
    "envConfig",
    "env_to_settings",
    "load_env_settings",
    "settings_to_env",
)
_reg("fd", "FDUtil")

_SUBMODULES = frozenset({"media", "envConfig", "fd", "scrapyRunner", "blackboxprotobuf"})

__all__ = sorted(set(_EXPORTS) | set(_SUBMODULES))


def resolve_utils_export(name: str):
    if name in _SUBMODULES:
        return import_module(f"{_UTILS_PKG}.{name}")
    if name not in _EXPORTS:
        raise AttributeError(f"module {_UTILS_PKG!r} has no attribute {name!r}")
    mod = import_module(f"{_UTILS_PKG}.{_EXPORTS[name]}")
    return getattr(mod, name)
