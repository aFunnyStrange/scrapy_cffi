"""Provide the compatibility facade for the selected Protobuf platform."""

from typing import Dict, List, Tuple, Union

from . import blackboxprotobuf


class ProtobufFactory:
    """Encode and decode Protobuf messages with optional Rust acceleration."""

    @staticmethod
    def protobuf_encode(data: Dict, typedef: Dict) -> bytes:
        """Encode one dictionary with the selected Protobuf backend."""
        return blackboxprotobuf.encode_message(data, typedef)

    @staticmethod
    def protobuf_decode(data: bytes) -> Tuple[Dict, Dict]:
        """Decode one message and return its inferred reusable definition."""
        decoded, typedef = blackboxprotobuf.decode_message(data)
        return decoded, typedef

    @staticmethod
    def backend_name() -> str:
        """Return ``rust`` or ``python`` for operational diagnostics."""
        return blackboxprotobuf.get_backend_name()

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

    @staticmethod
    def grpc_encode(data: Dict, typedef: Dict, is_gzip: bool = False) -> bytes:
        """Encode one message into a gRPC frame with optional gzip."""
        return blackboxprotobuf.grpc_encode(data, typedef, is_gzip)

    @staticmethod
    def grpc_stream_encode(
        data: List[Tuple[Dict, Dict]],
        is_gzip: bool = False,
    ) -> bytes:
        """Encode several message/type pairs into one gRPC byte stream."""
        return blackboxprotobuf.grpc_stream_encode(data, is_gzip)

    @staticmethod
    def grpc_decode(
        data: bytes,
    ) -> Union[Tuple[Dict, Dict], List[Tuple[Dict, Dict]]]:
        """Decode one or more concatenated gRPC frames."""
        return blackboxprotobuf.grpc_decode(data)


__all__ = ["ProtobufFactory"]
