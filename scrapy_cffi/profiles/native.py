"""Preserve historical native-profile imports over the platform boundary."""

from ..platform.curl_native import (
    CurlNativeActivationError as NativeActivationError,
    CurlNativeRuntimeInfo as ActivationInfo,
    activate_curl_native_runtime as activate_native,
    get_curl_native_runtime_info as get_activation_info,
)

__all__ = [
    "ActivationInfo",
    "NativeActivationError",
    "activate_native",
    "get_activation_info",
]
