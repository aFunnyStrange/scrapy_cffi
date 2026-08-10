"""Expose lightweight standalone helpers without constructing infrastructure."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scrapy_cffi.dupefilter.fingerprint import (
        build_fingerprint_bytes,
        canonical_request_url,
        fingerprint_sha1,
    )
    from scrapy_cffi.settings import SettingsInfo, merge_spider_settings

__all__ = [
    "canonical_request_url",
    "build_fingerprint_bytes",
    "fingerprint_sha1",
    "SettingsInfo",
    "merge_spider_settings",
]

_FINGERPRINT = frozenset(
    {"canonical_request_url", "build_fingerprint_bytes", "fingerprint_sha1"}
)
_SETTINGS = frozenset({"SettingsInfo", "merge_spider_settings"})


def __getattr__(name: str) -> Any:
    """Resolve one typed lightweight tool export lazily."""
    if name in _FINGERPRINT:
        module = import_module("scrapy_cffi.dupefilter.fingerprint")
        return getattr(module, name)
    if name in _SETTINGS:
        module = import_module("scrapy_cffi.settings")
        return getattr(module, name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    """Return the stable standalone helper surface."""
    return list(__all__)
