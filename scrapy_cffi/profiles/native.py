"""Load an ABI-compatible external curl_cffi wrapper before the vendor package."""

import importlib.machinery
import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import List, Optional, Union


class NativeActivationError(RuntimeError):
    """Report an invalid native directory, ABI, or import order."""


@dataclass(frozen=True)
class ActivationInfo:
    """Describe the external native wrapper active in this process."""

    native_dir: Path
    wrapper_path: Path
    platform: str


_activation_info: Optional[ActivationInfo] = None
_dll_directory_handles: List[object] = []


def _find_wrapper(native_dir: Path) -> Path:
    """Find the extension module matching the running interpreter ABI."""
    for suffix in importlib.machinery.EXTENSION_SUFFIXES:
        candidate = native_dir / ("_wrapper" + suffix)
        if candidate.is_file():
            return candidate
    expected = ", ".join(
        "_wrapper" + suffix for suffix in importlib.machinery.EXTENSION_SUFFIXES
    )
    raise NativeActivationError(
        "No curl_cffi wrapper matching this Python ABI was found in %s. "
        "Expected one of: %s" % (native_dir, expected)
    )


def _ensure_import_order() -> None:
    """Reject activation after curl_cffi has selected another wrapper."""
    imported = [
        name
        for name in sys.modules
        if name == "curl_cffi" or name.startswith("curl_cffi.")
    ]
    if imported:
        raise NativeActivationError(
            "Custom native activation must happen before importing curl_cffi; "
            "already imported: %s" % ", ".join(sorted(imported))
        )


def _load_wrapper(wrapper_path: Path) -> ModuleType:
    """Load the external extension under curl_cffi's expected module name."""
    module_name = "curl_cffi._wrapper"
    spec = importlib.util.spec_from_file_location(module_name, wrapper_path)
    if spec is None or spec.loader is None:
        raise NativeActivationError(
            "Unable to create an import spec for %s" % wrapper_path
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException as exc:
        sys.modules.pop(module_name, None)
        raise NativeActivationError(
            "Failed to load the custom curl_cffi wrapper. Confirm that its "
            "Python ABI and adjacent native libraries match the current runtime."
        ) from exc
    return module


def activate_native(native_dir: Union[str, Path]) -> ActivationInfo:
    """Activate one self-built curl_cffi wrapper for the current process.

    Native activation selects an implementation, not an impersonation profile.
    Every request must still pass ``impersonate`` explicitly.

    Args:
        native_dir: Directory containing ``_wrapper`` and adjacent DLL/SO files.

    Returns:
        Information about the activated native wrapper.

    Raises:
        NativeActivationError: If activation is late, incompatible, or invalid.
    """
    global _activation_info

    resolved_dir = Path(native_dir).expanduser().resolve()
    if _activation_info is not None:
        if _activation_info.native_dir != resolved_dir:
            raise NativeActivationError(
                "A different native directory is already active: %s"
                % _activation_info.native_dir
            )
        return _activation_info
    if not resolved_dir.is_dir():
        raise NativeActivationError(
            "Native directory does not exist: %s" % resolved_dir
        )

    _ensure_import_order()
    wrapper_path = _find_wrapper(resolved_dir)
    if os.name == "nt":
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is None:
            raise NativeActivationError("This Python runtime cannot add a DLL directory")
        _dll_directory_handles.append(add_dll_directory(str(resolved_dir)))

    _load_wrapper(wrapper_path)
    _activation_info = ActivationInfo(
        native_dir=resolved_dir,
        wrapper_path=wrapper_path,
        platform=sys.platform,
    )
    return _activation_info


def get_activation_info() -> Optional[ActivationInfo]:
    """Return the active external wrapper, or ``None`` for vendor defaults."""
    return _activation_info


__all__ = [
    "ActivationInfo",
    "NativeActivationError",
    "activate_native",
    "get_activation_info",
]
