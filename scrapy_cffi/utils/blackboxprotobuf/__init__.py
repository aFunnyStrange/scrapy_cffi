"""Expose accelerated Protobuf functions with a bundled Python fallback.

The bundled implementation is derived from NCC Group's MIT-licensed
``blackboxprotobuf`` project. When the optional ``pyblackboxprotobuf`` package
loads successfully, the public codec and gRPC functions are bound to its Rust
implementation once during import. Otherwise they remain bound to the bundled
pure-Python implementation.
"""

from typing import Optional, Tuple, Union

from scrapy_cffi.platform.protobuf import PythonProtobufCodec, select_protobuf_codec

from .api import decode_message as _python_decode_message
from .api import encode_message as _python_encode_message
from .config import Config
from .exceptions import DecoderException, EncoderException
from .pytypes import Message, TypeDefDict


_PYTHON_CODEC = PythonProtobufCodec(
    encode=_python_encode_message,
    decode=_python_decode_message,
)
_CODEC = select_protobuf_codec(_PYTHON_CODEC)

backend_name = _CODEC.backend_name
grpc_encode = _CODEC.grpc_encode
grpc_stream_encode = _CODEC.grpc_stream_encode
grpc_decode = _CODEC.grpc_decode

if backend_name == "python":
    encode_message = _python_encode_message
    decode_message = _python_decode_message
else:

    def encode_message(
        value: Message,
        message_type: Union[str, TypeDefDict],
        config: Optional[Config] = None,
    ) -> bytes:
        """Encode natively while preserving legacy named/configured typedefs."""
        if config is not None or isinstance(message_type, str):
            return _python_encode_message(value, message_type, config)
        try:
            return _CODEC.encode_message(value, message_type)
        except Exception as error:
            if type(error).__module__.startswith("pyblackboxprotobuf"):
                raise EncoderException(str(error)) from error
            raise

    def decode_message(
        buf: bytes,
        message_type: Optional[Union[str, TypeDefDict]] = None,
        config: Optional[Config] = None,
    ) -> Tuple[Message, TypeDefDict]:
        """Decode natively while preserving legacy named/configured typedefs."""
        if (
            config is not None
            or isinstance(buf, str)
            or isinstance(message_type, str)
        ):
            return _python_decode_message(buf, message_type, config)
        try:
            return _CODEC.decode_message(buf, message_type)
        except Exception as error:
            if type(error).__module__.startswith("pyblackboxprotobuf"):
                raise DecoderException(str(error)) from error
            raise


def get_backend_name() -> str:
    """Return the selected codec backend for diagnostics and tests."""
    return backend_name


__all__ = [
    "DecoderException",
    "EncoderException",
    "backend_name",
    "decode_message",
    "encode_message",
    "get_backend_name",
    "grpc_decode",
    "grpc_encode",
    "grpc_stream_encode",
]
