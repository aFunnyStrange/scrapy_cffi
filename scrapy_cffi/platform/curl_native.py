"""Activate an ABI-compatible curl_cffi native runtime once per process."""

import importlib.machinery
import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import List, Optional, Union


class CurlNativeActivationError(RuntimeError):
    """Report an invalid curl runtime directory, ABI, or import order."""


@dataclass(frozen=True)
class CurlNativeRuntimeInfo:
    """Describe the external curl runtime active in this process."""

    native_dir: Path
    wrapper_path: Path
    platform: str

    @property
    def runtime_dir(self) -> Path:
        """Expose the directory with transport-runtime terminology."""
        return self.native_dir


_runtime_info: Optional[CurlNativeRuntimeInfo] = None
_dll_directory_handles: List[object] = []


def _find_wrapper(runtime_dir: Path) -> Path:
    """Find the extension module matching the running interpreter ABI."""
    for suffix in importlib.machinery.EXTENSION_SUFFIXES:
        candidate = runtime_dir / ("_wrapper" + suffix)
        if candidate.is_file():
            return candidate
    expected = ", ".join(
        "_wrapper" + suffix for suffix in importlib.machinery.EXTENSION_SUFFIXES
    )
    raise CurlNativeActivationError(
        "No curl_cffi wrapper matching this Python ABI was found in %s. "
        "Expected one of: %s" % (runtime_dir, expected)
    )


def _ensure_import_order() -> None:
    """Reject activation after curl_cffi has selected another wrapper."""
    imported = [
        name
        for name in sys.modules
        if name == "curl_cffi" or name.startswith("curl_cffi.")
    ]
    if imported:
        raise CurlNativeActivationError(
            "Custom curl runtime activation must happen before importing "
            "curl_cffi; already imported: %s" % ", ".join(sorted(imported))
        )


def _load_wrapper(wrapper_path: Path) -> ModuleType:
    """Load the external extension under curl_cffi's expected module name."""
    module_name = "curl_cffi._wrapper"
    spec = importlib.util.spec_from_file_location(module_name, wrapper_path)
    if spec is None or spec.loader is None:
        raise CurlNativeActivationError(
            "Unable to create an import spec for %s" % wrapper_path
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException as exc:
        sys.modules.pop(module_name, None)
        raise CurlNativeActivationError(
            "Failed to load the custom curl_cffi wrapper. Confirm that its "
            "Python ABI and adjacent native libraries match the current runtime."
        ) from exc
    return module


def activate_curl_native_runtime(
    runtime_dir: Union[str, Path],
) -> CurlNativeRuntimeInfo:
    """Select one process-wide curl_cffi implementation before vendor import."""
    global _runtime_info

    resolved_dir = Path(runtime_dir).expanduser().resolve()
    if _runtime_info is not None:
        if _runtime_info.runtime_dir != resolved_dir:
            raise CurlNativeActivationError(
                "A different curl runtime directory is already active: %s"
                % _runtime_info.runtime_dir
            )
        return _runtime_info
    if not resolved_dir.is_dir():
        raise CurlNativeActivationError(
            "Curl runtime directory does not exist: %s" % resolved_dir
        )

    _ensure_import_order()
    wrapper_path = _find_wrapper(resolved_dir)
    if os.name == "nt":
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is None:
            raise CurlNativeActivationError(
                "This Python runtime cannot add a DLL directory"
            )
        _dll_directory_handles.append(add_dll_directory(str(resolved_dir)))

    _load_wrapper(wrapper_path)
    _runtime_info = CurlNativeRuntimeInfo(
        native_dir=resolved_dir,
        wrapper_path=wrapper_path,
        platform=sys.platform,
    )
    return _runtime_info


def get_curl_native_runtime_info() -> Optional[CurlNativeRuntimeInfo]:
    """Return the selected curl runtime or ``None`` for vendor defaults."""
    return _runtime_info


__all__ = [
    "CurlNativeActivationError",
    "CurlNativeRuntimeInfo",
    "activate_curl_native_runtime",
    "get_curl_native_runtime_info",
]
