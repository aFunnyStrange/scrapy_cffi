"""Compact, versioned JSON serialization for scheduler state."""

import json
import zlib
from typing import Any


_MAGIC = b"SCF1"
_RAW = b"J"
_ZLIB = b"Z"
MAX_STATE_BYTES = 16 * 1024 * 1024


def encode_state(
    value: Any,
    compression_level: int = 6,
    max_size: int = MAX_STATE_BYTES,
) -> bytes:
    """Encode JSON and keep compression only when it actually saves space."""
    raw = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(raw) > max_size:
        raise ValueError(
            f"scheduler state exceeds the {max_size}-byte logical size limit"
        )
    compressed = zlib.compress(raw, level=compression_level)
    if len(compressed) < len(raw):
        return _MAGIC + _ZLIB + compressed
    return _MAGIC + _RAW + raw


def decode_state(payload: bytes, max_size: int = MAX_STATE_BYTES) -> Any:
    """Decode state produced by :func:`encode_state`."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("scheduler state payload must be bytes-like")
    payload = bytes(payload)
    if not payload.startswith(_MAGIC) or len(payload) <= len(_MAGIC):
        raise ValueError("unsupported scheduler state format")

    encoding = payload[len(_MAGIC):len(_MAGIC) + 1]
    data = payload[len(_MAGIC) + 1:]
    if encoding == _ZLIB:
        decompressor = zlib.decompressobj()
        data = decompressor.decompress(data, max_size + 1)
        if len(data) > max_size or decompressor.unconsumed_tail:
            raise ValueError(
                f"decompressed scheduler state exceeds the {max_size}-byte limit"
            )
        remaining = max_size + 1 - len(data)
        data += decompressor.flush(remaining)
        if len(data) > max_size:
            raise ValueError(
                f"decompressed scheduler state exceeds the {max_size}-byte limit"
            )
        if not decompressor.eof or decompressor.unused_data:
            raise ValueError("invalid compressed scheduler state")
    elif encoding != _RAW:
        raise ValueError("unsupported scheduler state encoding")
    elif len(data) > max_size:
        raise ValueError(f"scheduler state exceeds the {max_size}-byte limit")
    return json.loads(data.decode("utf-8"))


__all__ = ["MAX_STATE_BYTES", "encode_state", "decode_state"]
