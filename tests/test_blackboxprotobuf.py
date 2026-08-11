"""Verify Protobuf backend selection, fallback, and codec parity."""

import logging
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple, Union

import pytest

from scrapy_cffi.platform.protobuf import (
    PythonProtobufCodec,
    select_protobuf_codec,
)
from scrapy_cffi.utils import blackboxprotobuf
from scrapy_cffi.utils.blackboxprotobuf.api import (
    decode_message as python_decode_message,
)
from scrapy_cffi.utils.blackboxprotobuf.api import (
    encode_message as python_encode_message,
)
from scrapy_cffi.utils.blackboxprotobuf.config import Config
from scrapy_cffi.utils.protobuf import ProtobufFactory


BytesLike = Union[bytes, bytearray, memoryview]


def _fixture() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return a message that exercises strings, bytes, and integers."""
    payload = {"1": "aaa", "2": b"\xff\x00", "3": 7}
    typedef = {
        "1": {"type": "string"},
        "2": {"type": "bytes"},
        "3": {"type": "uint"},
    }
    return payload, typedef


def _python_codec() -> PythonProtobufCodec:
    """Build the bundled fallback through the stable platform adapter."""
    return PythonProtobufCodec(
        encode=python_encode_message,
        decode=python_decode_message,
    )


def test_blackboxprotobuf_round_trip_uses_selected_backend() -> None:
    """The compatibility import must round-trip with either selected backend."""
    payload, typedef = _fixture()

    encoded = blackboxprotobuf.encode_message(payload, typedef)
    decoded, decoded_typedef = blackboxprotobuf.decode_message(encoded)

    assert decoded == payload
    assert decoded_typedef["1"]["type"] == "string"
    assert decoded_typedef["2"]["type"] == "bytes"
    assert blackboxprotobuf.get_backend_name() in {"python", "rust"}
    assert ProtobufFactory.backend_name() == blackboxprotobuf.get_backend_name()


def test_missing_optional_package_selects_python_once() -> None:
    """An absent accelerator must silently retain the bundled implementation."""
    imports = []

    def missing_import(name: str) -> Any:
        """Simulate the optional package not being installed."""
        imports.append(name)
        raise ModuleNotFoundError(name=name)

    codec = select_protobuf_codec(_python_codec(), importer=missing_import)
    payload, typedef = _fixture()

    first = codec.encode_message(payload, typedef)
    second = codec.encode_message(payload, typedef)

    assert codec.backend_name == "python"
    assert first == second
    assert imports == ["pyblackboxprotobuf"]


def test_native_package_selects_rust_and_binds_callables_once() -> None:
    """A healthy native module must be selected without hot-path imports."""
    imports = []
    calls = []

    def native_encode(value: Dict[str, Any], typedef: Dict[str, Any]) -> bytes:
        """Record a fake native encode call."""
        calls.append((value, typedef))
        return b"native"

    def native_decode(
        data: BytesLike,
        message_type: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Return a fake native decode result."""
        del data, message_type
        return {"1": 1}, {"1": {"type": "int"}}

    def native_import(name: str) -> Any:
        """Return one protocol-compatible native module."""
        imports.append(name)
        return SimpleNamespace(
            encode_message=native_encode,
            decode_message=native_decode,
        )

    codec = select_protobuf_codec(_python_codec(), importer=native_import)
    codec.encode_message({"1": 1}, {"1": {"type": "int"}})
    codec.encode_message({"1": 2}, {"1": {"type": "int"}})
    frame = codec.grpc_encode({"1": 3}, {"1": {"type": "int"}})
    grpc_decoded = codec.grpc_decode(frame)

    assert codec.backend_name == "rust"
    assert imports == ["pyblackboxprotobuf"]
    assert len(calls) == 3
    assert frame[5:] == b"native"
    assert grpc_decoded == ({"1": 1}, {"1": {"type": "int"}})


def test_broken_native_package_warns_and_falls_back(caplog: pytest.LogCaptureFixture) -> None:
    """An installed but incompatible accelerator must not disable Protobuf."""

    def broken_import(name: str) -> Any:
        """Return a module missing the required public functions."""
        del name
        return SimpleNamespace()

    with caplog.at_level(logging.WARNING, logger="scrapy_cffi.platform.protobuf"):
        codec = select_protobuf_codec(_python_codec(), importer=broken_import)

    assert codec.backend_name == "python"
    assert "using Python fallback" in caplog.text


def test_unloadable_native_library_warns_and_falls_back(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A missing platform DLL/shared object must retain working Python code."""

    def unloadable_import(name: str) -> Any:
        """Simulate a native dynamic-library load failure."""
        del name
        raise OSError("native library is unavailable")

    with caplog.at_level(logging.WARNING, logger="scrapy_cffi.platform.protobuf"):
        codec = select_protobuf_codec(_python_codec(), importer=unloadable_import)

    assert codec.backend_name == "python"
    assert "OSError" in caplog.text
    assert "using Python fallback" in caplog.text


def test_native_and_python_backends_have_identical_common_contract() -> None:
    """Compare the installed Rust accelerator with the bundled codec when available."""
    native = pytest.importorskip("pyblackboxprotobuf")
    payload, typedef = _fixture()

    python_encoded = python_encode_message(payload, typedef)
    native_encoded = native.encode_message(payload, typedef)

    assert native_encoded == python_encoded
    assert native.decode_message(native_encoded) == python_decode_message(
        python_encoded
    )
    native_frame = native.ProtobufFactory.grpc_encode(payload, typedef)
    framework_frame = ProtobufFactory.grpc_encode(payload, typedef)
    assert framework_frame == native_frame
    assert ProtobufFactory.grpc_decode(framework_frame)[0] == payload


def test_grpc_helpers_continue_through_selected_codec() -> None:
    """The public factory must preserve gzip and multi-frame behavior."""
    payload, typedef = _fixture()
    messages = [(payload, typedef), (payload, typedef)]

    encoded = ProtobufFactory.grpc_stream_encode(messages, is_gzip=True)
    decoded = ProtobufFactory.grpc_decode(encoded)

    assert isinstance(decoded, list)
    assert [message for message, _ in decoded] == [payload, payload]
    assert blackboxprotobuf.grpc_stream_encode(messages, True) == encoded


@pytest.mark.parametrize(
    "invalid_frame",
    [
        b"\x00",
        b"\x02\x00\x00\x00\x00",
        b"\x00\x00\x00\x00\x03x",
    ],
)
def test_grpc_platform_rejects_invalid_frames(invalid_frame: bytes) -> None:
    """The shared framing contract must reject truncated or invalid input."""
    with pytest.raises(ValueError):
        blackboxprotobuf.grpc_decode(invalid_frame)


def test_legacy_named_typedef_and_config_remain_available() -> None:
    """Rust selection must not remove the bundled configurable API surface."""
    payload, typedef = _fixture()
    config = Config()
    config.known_types["fixture"] = typedef

    encoded = blackboxprotobuf.encode_message(payload, "fixture", config)
    decoded, _ = blackboxprotobuf.decode_message(encoded, None, config)

    assert decoded == payload
