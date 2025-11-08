# utils/fixed.py
import struct
import binascii
from ..exceptions import DecoderException, EncoderException
from typing import Any, Tuple

# Generic functions for encoding/decoding structs based on the "struct" format
def encode_struct(fmt: str, value: Any) -> bytes:
    """Generic method for encoding arbitrary python "struct" values"""
    try:
        return struct.pack(fmt, value)
    except struct.error as exc:
        raise EncoderException(
            "Error encoding value %r with format string %s" % (value, fmt)
        )

def decode_struct(fmt: str, buf: bytes, pos: int) -> Tuple[Any, int]:
    """Generic method for decoding arbitrary python "struct" values"""
    new_pos = pos + struct.calcsize(fmt)
    try:
        return struct.unpack(fmt, buf[pos:new_pos])[0], new_pos
    except struct.error as exc:
        raise DecoderException(
            "Error deocding format string %s from bytes: %r"
            % (fmt, binascii.hexlify(buf[pos:new_pos]))
        )

def encode_fixed32(value: Any) -> bytes:
    """Encode a single 32 bit fixed-size value"""
    return encode_struct("<I", value)

def decode_fixed32(buf: bytes, pos: int) -> Tuple[Any, int]:
    """Decode a single 32 bit fixed-size value"""
    return decode_struct("<I", buf, pos)

def encode_sfixed32(value: Any) -> bytes:
    """Encode a single signed 32 bit fixed-size value"""
    return encode_struct("<i", value)

def decode_sfixed32(buf: bytes, pos: int) -> Tuple[Any, int]:
    """Decode a single signed 32 bit fixed-size value"""
    return decode_struct("<i", buf, pos)

def encode_float(value: Any) -> bytes:
    """Encode a single 32 bit floating point value"""
    return encode_struct("<f", value)

def decode_float(buf: bytes, pos: int) -> Tuple[Any, int]:
    """Decode a single 32 bit floating point value"""
    return decode_struct("<f", buf, pos)

def encode_fixed64(value: Any) -> bytes:
    """Encode a single 64 bit fixed-size value"""
    return encode_struct("<Q", value)

def decode_fixed64(buf: bytes, pos: int) -> Tuple[Any, int]:
    """Decode a single 64 bit fixed-size value"""
    return decode_struct("<Q", buf, pos)

def encode_sfixed64(value: Any) -> bytes:
    """Encode a single signed 64 bit fixed-size value"""
    return encode_struct("<q", value)

def decode_sfixed64(buf: bytes, pos: int) -> Tuple[Any, int]:
    """Decode a single signed 64 bit fixed-size value"""
    return decode_struct("<q", buf, pos)

def encode_double(value: Any) -> bytes:
    """Encode a single 64 bit floating point value"""
    return encode_struct("<d", value)

def decode_double(buf: bytes, pos: int) -> Tuple[Any, int]:
    """Decode a single 64 bit floating point value"""
    return decode_struct("<d", buf, pos)
