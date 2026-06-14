from ._version import __version__

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

_LAZY_SUBMODULES = {
    "crawler",
}


def __getattr__(name: str):
    if name in _LAZY_RUNNER:
        from . import runner as _runner

        return getattr(_runner, name)
    if name in _LAZY_UTILS:
        from .utils._exports import resolve_utils_export

        return resolve_utils_export(name)
    if name in _LAZY_SETTINGS:
        from .settings import SettingsInfo, merge_spider_settings

        return SettingsInfo if name == "SettingsInfo" else merge_spider_settings
    if name in _LAZY_SUBMODULES:
        import importlib

        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
