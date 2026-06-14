"""
Filesystem paths for ctypes C extension resources.

Load order (see ``CExtensionLoader``):
  project ``cpy_resources`` → system store → framework ``cpy/cpy_resources``
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ENV_CPY_DIR = "SCRAPY_CFFI_CPY_DIR"


def get_system_cpy_root() -> Path:
    """
    User-writable directory for globally installed C extension modules.

    Override with ``SCRAPY_CFFI_CPY_DIR``. Default:

    - Windows: ``%LOCALAPPDATA%\\scrapy_cffi\\cpy_resources``
    - macOS/Linux: ``~/.local/share/scrapy_cffi/cpy_resources``
      (respects ``XDG_DATA_HOME`` when set)
    """
    override = os.environ.get(_ENV_CPY_DIR)
    if override:
        return Path(override).expanduser().resolve()

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "scrapy_cffi" / "cpy_resources"

    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "scrapy_cffi" / "cpy_resources"
    return Path.home() / ".local" / "share" / "scrapy_cffi" / "cpy_resources"


def get_framework_cpy_root() -> Path:
    return Path(__file__).resolve().parent / "cpy_resources"


__all__ = [
    "get_system_cpy_root",
    "get_framework_cpy_root",
]
