"""Compose native wrapper activation with optional profile registration."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Union

from .native import ActivationInfo, activate_native
from .registry import (
    DEFAULT_REGISTRY,
    ProfileRegistry,
    ProfileSpec,
    load_profile_manifest,
)


@dataclass(frozen=True)
class ProfileRuntimeInfo:
    """Describe native activation and aliases loaded for one runtime."""

    native: ActivationInfo
    profiles: List[ProfileSpec]


def activate_profile_runtime(
    native_dir: Union[str, Path],
    registry: ProfileRegistry = DEFAULT_REGISTRY,
) -> ProfileRuntimeInfo:
    """Activate a self-built wrapper and register its optional manifest."""
    native = activate_native(native_dir)
    profiles = load_profile_manifest(native.native_dir, registry=registry)
    return ProfileRuntimeInfo(native=native, profiles=profiles)


__all__ = ["ProfileRuntimeInfo", "activate_profile_runtime"]
