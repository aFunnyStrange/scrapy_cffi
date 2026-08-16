"""Expose request-scoped TLS profiles and optional native activation."""

from .native import (
    ActivationInfo,
    NativeActivationError,
    activate_native,
    get_activation_info,
)
from .registry import (
    ClientHintItems,
    DEFAULT_REGISTRY,
    ImpersonateResolver,
    PROFILE_MANIFEST_NAME,
    PROFILE_MANIFEST_SCHEMA_VERSION,
    ProfileManifestError,
    ProfileRegistry,
    ProfileSpec,
    get_impersonate_resolver,
    load_profile_manifest,
    register_profile,
    resolve_impersonate,
)
from .runtime import ProfileRuntimeInfo, activate_profile_runtime

__all__ = [
    "ActivationInfo",
    "ClientHintItems",
    "DEFAULT_REGISTRY",
    "ImpersonateResolver",
    "NativeActivationError",
    "PROFILE_MANIFEST_NAME",
    "PROFILE_MANIFEST_SCHEMA_VERSION",
    "ProfileManifestError",
    "ProfileRegistry",
    "ProfileRuntimeInfo",
    "ProfileSpec",
    "activate_native",
    "activate_profile_runtime",
    "get_activation_info",
    "get_impersonate_resolver",
    "load_profile_manifest",
    "register_profile",
    "resolve_impersonate",
]
