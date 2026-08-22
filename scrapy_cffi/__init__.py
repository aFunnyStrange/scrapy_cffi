"""Expose the stable lazy public API for scrapy_cffi."""

from ._version import __version__
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .composition import build_resource_service
    from .crawler import Crawler
    from .runner import (
        SpiderRunConfig,
        cleanup_loop,
        run_all_spiders,
        run_all_spiders_sync,
        run_spider,
        run_spider_sync,
        run_spiders,
        run_spiders_sync,
    )
    from .settings import SettingsInfo, merge_spider_settings
    from .runtime import Resource, ResourceContext, ResourceService
    from .utils.common import load_settings_with_path
    from .utils.log import init_logger

__all__ = [
    "__version__",
    "run_spider",
    "run_all_spiders",
    "run_spider_sync",
    "run_all_spiders_sync",
    "run_spiders",
    "run_spiders_sync",
    "SpiderRunConfig",
    "Crawler",
    "cleanup_loop",
    "load_settings_with_path",
    "init_logger",
    "merge_spider_settings",
    "SettingsInfo",
    "build_resource_service",
    "Resource",
    "ResourceContext",
    "ResourceService",
]

_LAZY_RUNNER = {
    "run_spider",
    "run_all_spiders",
    "run_spider_sync",
    "run_all_spiders_sync",
    "run_spiders",
    "run_spiders_sync",
    "SpiderRunConfig",
    "Crawler",
    "cleanup_loop",
}

_LAZY_UTILS = {
    "load_settings_with_path",
    "init_logger",
}

_LAZY_SETTINGS = {
    "merge_spider_settings",
    "SettingsInfo",
}

_LAZY_COMPOSITION = {"build_resource_service"}

_LAZY_RUNTIME = {"Resource", "ResourceContext", "ResourceService"}

_LAZY_SUBMODULES = {
    "crawler",
    "infra",
    "repo",
    "service",
}


def __getattr__(name: str) -> Any:
    """Resolve the typed lazy package surface."""
    if name in _LAZY_RUNNER:
        from . import runner as _runner

        return getattr(_runner, name)
    if name in _LAZY_UTILS:
        from .utils._exports import resolve_utils_export

        return resolve_utils_export(name)
    if name in _LAZY_SETTINGS:
        from .settings import SettingsInfo, merge_spider_settings

        return SettingsInfo if name == "SettingsInfo" else merge_spider_settings
    if name in _LAZY_COMPOSITION:
        from .composition import build_resource_service

        return build_resource_service
    if name in _LAZY_RUNTIME:
        from . import runtime as _runtime

        return getattr(_runtime, name)
    if name in _LAZY_SUBMODULES:
        import importlib

        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """Return public package exports for IDE completion and inspection."""
    return list(__all__)
