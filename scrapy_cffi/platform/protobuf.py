"""Define the stable Protobuf codec contract and optional Rust adapter."""

import gzip
import logging
from importlib import import_module
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, Union, cast


Message = Dict[Any, Any]
TypeDefinition = Dict[str, Any]
BytesLike = Union[bytes, bytearray, memoryview]
CodecCallable = Callable[..., Any]
GrpcMessage = Tuple[Message, TypeDefinition]
GrpcResult = Union[GrpcMessage, List[GrpcMessage]]

logger = logging.getLogger(__name__)


class ProtobufCodecProtocol(Protocol):
    """Describe the synchronous codec capability consumed by the framework."""

    backend_name: str

    def encode_message(
        self,
        value: Message,
        message_type: TypeDefinition,
    ) -> bytes:
        """Encode one dictionary using a reusable Protobuf type definition."""
        ...

    def decode_message(
        self,
        data: BytesLike,
        message_type: Optional[TypeDefinition] = None,
    ) -> Tuple[Message, TypeDefinition]:
        """Decode bytes and return both the message and completed definition."""
        ...

    def grpc_encode(
        self,
        data: Message,
        typedef: TypeDefinition,
        is_gzip: bool = False,
    ) -> bytes:
        """Encode one Protobuf message into a gRPC data frame."""
        ...

    def grpc_stream_encode(
        self,
        data: List[GrpcMessage],
        is_gzip: bool = False,
    ) -> bytes:
        """Encode several messages into one concatenated gRPC byte stream."""
        ...

    def grpc_decode(self, data: bytes) -> GrpcResult:
        """Decode one or more framed gRPC messages."""
        ...


class _GrpcFramingCodec:
    """Own framework-stable gRPC framing around a concrete payload codec."""

    def encode_message(
        self,
        value: Message,
        message_type: TypeDefinition,
    ) -> bytes:
        """Require a concrete payload encoder from the selected adapter."""
        raise NotImplementedError

    def decode_message(
        self,
        data: BytesLike,
        message_type: Optional[TypeDefinition] = None,
    ) -> Tuple[Message, TypeDefinition]:
        """Require a concrete payload decoder from the selected adapter."""
        raise NotImplementedError

    @staticmethod
    def encode_message_length(length: int) -> bytes:
        """Encode a gRPC four-byte big-endian message length."""
        if not 0 <= length <= 0xFFFFFFFF:
            raise ValueError("Message length must be between 0 and 2^32-1")
        return length.to_bytes(4, byteorder="big")

    @staticmethod
    def decode_message_length(data: bytes) -> int:
        """Decode a gRPC four-byte big-endian message length."""
        if len(data) != 4:
            raise ValueError("Expected 4 bytes for message length")
        return int.from_bytes(data, byteorder="big")

    def grpc_encode(
        self,
        data: Message,
        typedef: TypeDefinition,
        is_gzip: bool = False,
    ) -> bytes:
        """Encode one Protobuf message into a gRPC data frame."""
        encoded = self.encode_message(data, typedef)
        if is_gzip:
            encoded = gzip.compress(encoded)
        return (
            bytes([int(is_gzip)])
            + self.encode_message_length(len(encoded))
            + encoded
        )

    def grpc_stream_encode(
        self,
        data: List[GrpcMessage],
        is_gzip: bool = False,
    ) -> bytes:
        """Encode several messages into one concatenated gRPC byte stream."""
        return b"".join(
            self.grpc_encode(message, typedef, is_gzip)
            for message, typedef in data
        )

    def grpc_decode(self, data: bytes) -> GrpcResult:
        """Decode one or more framed gRPC messages."""
        results = []
        offset = 0
        total_length = len(data)
        while offset < total_length:
            if total_length - offset < 5:
                raise ValueError("Incomplete grpc message header")
            compression = data[offset]
            offset += 1
            if compression not in (0, 1):
                raise ValueError(
                    "Unsupported grpc compression flag: %d" % compression
                )
            message_length = self.decode_message_length(data[offset : offset + 4])
            offset += 4
            if total_length - offset < message_length:
                raise ValueError("Incomplete grpc message body")
            payload = data[offset : offset + message_length]
            offset += message_length
            if compression == 1:
                payload = gzip.decompress(payload)
            results.append(self.decode_message(payload))
        return results[0] if len(results) == 1 else results


class PythonProtobufCodec(_GrpcFramingCodec):
    """Adapt scrapy_cffi's bundled pure-Python implementation."""

    backend_name = "python"

    def __init__(
        self,
        encode: CodecCallable,
        decode: CodecCallable,
    ) -> None:
        """Bind the fallback callables once during module composition."""
        self._encode = encode
        self._decode = decode

    def encode_message(
        self,
        value: Message,
        message_type: TypeDefinition,
    ) -> bytes:
        """Encode through the bundled Python implementation."""
        return cast(bytes, self._encode(value, message_type))

    def decode_message(
        self,
        data: BytesLike,
        message_type: Optional[TypeDefinition] = None,
    ) -> Tuple[Message, TypeDefinition]:
        """Decode through the bundled Python implementation."""
        return cast(
            Tuple[Message, TypeDefinition],
            self._decode(bytes(data), message_type),
        )


class RustProtobufCodec(_GrpcFramingCodec):
    """Adapt the optional pyblackboxprotobuf native package."""

    backend_name = "rust"

    def __init__(
        self,
        encode: CodecCallable,
        decode: CodecCallable,
    ) -> None:
        """Bind the native callables once so the hot path has no lookup branch."""
        self._encode = encode
        self._decode = decode

    def encode_message(
        self,
        value: Message,
        message_type: TypeDefinition,
    ) -> bytes:
        """Encode through the Rust implementation."""
        return cast(bytes, self._encode(value, message_type))

    def decode_message(
        self,
        data: BytesLike,
        message_type: Optional[TypeDefinition] = None,
    ) -> Tuple[Message, TypeDefinition]:
        """Decode through the Rust implementation."""
        return cast(
            Tuple[Message, TypeDefinition],
            self._decode(data, message_type),
        )


def select_protobuf_codec(
    python_codec: ProtobufCodecProtocol,
    importer: Callable[[str], Any] = import_module,
) -> ProtobufCodecProtocol:
    """Prefer pyblackboxprotobuf and safely retain the bundled fallback.

    A missing optional package is an expected development configuration and is
    therefore silent. A present but unloadable or API-incompatible native
    package emits one warning before falling back to the pure-Python codec.
    """
    try:
        native_module = importer("pyblackboxprotobuf")
        encode = getattr(native_module, "encode_message")
        decode = getattr(native_module, "decode_message")
        if not callable(encode) or not callable(decode):
            raise TypeError("native encode_message/decode_message must be callable")
    except ModuleNotFoundError as error:
        if error.name != "pyblackboxprotobuf":
            logger.warning(
                "pyblackboxprotobuf could not load dependency %s; using Python fallback",
                error.name,
            )
        return python_codec
    except Exception as error:
        logger.warning(
            "pyblackboxprotobuf is unavailable (%s: %s); using Python fallback",
            type(error).__name__,
            error,
        )
        return python_codec
    return RustProtobufCodec(encode=encode, decode=decode)


__all__ = [
    "BytesLike",
    "GrpcMessage",
    "GrpcResult",
    "Message",
    "ProtobufCodecProtocol",
    "PythonProtobufCodec",
    "RustProtobufCodec",
    "TypeDefinition",
    "select_protobuf_codec",
]
