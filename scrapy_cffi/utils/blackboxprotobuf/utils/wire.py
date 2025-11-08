# utils/wire.py
import binascii
from ..schema import VarInt
from ..exceptions import EncoderException, DecoderException
from typing import Any, Tuple

def encode_uvarint(value: Any) -> bytes:
    """Encode a long or int into a bytearray."""
    if not isinstance(value, int):
        raise EncoderException("Got non-int type for uvarint encoding: %s" % value)
    output = bytearray()
    if value < VarInt.MIN_UVARINT:
        raise EncoderException(
            "Error encoding %d as uvarint. Value must be positive" % value
        )
    if value > VarInt.MAX_UVARINT:
        raise EncoderException(
            "Error encoding %d as uvarint. Value must be %s or less"
            % (value, VarInt.MAX_UVARINT)
        )

    if not value:
        output.append(value & 0x7F)
    else:
        while value:
            next_byte = value & 0x7F
            value >>= 7
            if value:
                next_byte |= 0x80
            output.append(next_byte)

    return output

def decode_uvarint(buf: bytes, pos: int) -> Tuple[int, int]:
    """Decode bytearray into a long."""
    pos_start = pos
    # Convert buffer to string
    try:
        value = 0
        shift = 0
        while buf[pos] & 0x80:
            value += (buf[pos] & 0x7F) << (shift * 7)
            pos += 1
            shift += 1
        value += (buf[pos] & 0x7F) << (shift * 7)
        pos += 1
    except IndexError:
        raise DecoderException(
            "Error decoding uvarint: read past the end of the buffer"
        )

    # Validate that this is a cononical encoding by re-encoding the value
    try:
        test_encode = encode_uvarint(value)
    except EncoderException as ex:
        raise DecoderException(
            "Error decoding uvarint: value (%s) was not able to be re-encoded: %s"
            % (value, ex)
        )
    if buf[pos_start:pos] != test_encode:
        raise DecoderException(
            "Error decoding uvarint: Encoding is not standard:\noriginal:  %r\nstandard: %r"
            % (buf[pos_start:pos], test_encode)
        )

    return (value, pos)


def encode_varint(value: Any) -> bytes:
    """Encode a long or int into a bytearray."""
    if not isinstance(value, int):
        raise EncoderException("Got non-int type for varint encoding: %s" % value)
    if value > VarInt.MAX_SVARINT:
        raise EncoderException(
            "Error encoding %d as varint. Value must be <= %s" % (value, VarInt.MAX_SVARINT.value)
        )
    if value < VarInt.MIN_SVARINT:
        raise EncoderException(
            "Error encoding %d as varint. Value must be >= %s" % (value, VarInt.MIN_SVARINT.value)
        )
    if value < 0:
        value += 1 << 64
    output = encode_uvarint(value)
    return output


def decode_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    """Decode bytearray into a long."""
    # Convert buffer to string
    pos_start = pos

    value, pos = decode_uvarint(buf, pos)
    if value & (1 << 63):
        value -= 1 << 64

    # Validate that this is a cononical encoding by re-encoding the value
    try:
        test_encode = encode_varint(value)
    except EncoderException as ex:
        raise DecoderException(
            "Error decoding varint: value (%s) was not able to be re-encoded: %s"
            % (value, ex)
        )

    if buf[pos_start:pos] != test_encode:
        raise DecoderException(
            "Error decoding varint: Encoding is not standard:\noriginal:  %r\nstandard: %r"
            % (buf[pos_start:pos], test_encode)
        )
    return (value, pos)


def encode_zig_zag(value: int) -> int:
    if value < 0:
        return (abs(value) << 1) - 1
    return value << 1


def decode_zig_zag(value: int) -> int:
    if value & 0x1:
        # negative
        return -((value + 1) >> 1)
    return value >> 1


def encode_svarint(value: Any) -> bytes:
    """Zigzag encode the potentially signed value prior to encoding"""
    if not isinstance(value, int):
        raise EncoderException("Got non-int type for svarint encoding: %s" % value)
    # zigzag encode value
    if value > VarInt.MAX_SVARINT:
        raise EncoderException(
            "Error encoding %d as svarint. Value must be <= %s" % (value, VarInt.MAX_SVARINT)
        )
    if value < VarInt.MIN_SVARINT:
        raise EncoderException(
            "Error encoding %d as svarint. Value must be >= %s" % (value, VarInt.MIN_SVARINT)
        )
    return encode_uvarint(encode_zig_zag(value))


def decode_svarint(buf: bytes, pos: int) -> Tuple[int, int]:
    """Decode bytearray into a long."""
    pos_start = pos

    output, pos = decode_uvarint(buf, pos)
    value = decode_zig_zag(output)

    # Validate that this is a cononical encoding by re-encoding the value
    test_encode = encode_svarint(value)
    if buf[pos_start:pos] != test_encode:
        raise DecoderException(
            "Error decoding svarint: Encoding is not standard:\noriginal:  %r\nstandard: %r"
            % (buf[pos_start:pos], test_encode)
        )

    return value, pos

def encode_string(value: Any) -> bytes:
    """Encode a string as a length delimited byte array"""
    try:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        elif not isinstance(value, str):
            raise TypeError("not expecting type '%s'" % type(value))
    except TypeError as exc:
        raise EncoderException("Error encoding string to message: %r" % value) from exc
    return encode_bytes(value)


def encode_bytes(value: Any) -> bytes:
    """Encode a length delimited byte array"""
    if isinstance(value, bytearray):
        value = bytes(value)
    try:
        if isinstance(value, str):
            value = value.encode("utf-8")
        if not isinstance(value, bytes):
            raise TypeError("not expecting type '%s'" % type(value))
    except TypeError as exc:
        raise EncoderException("Error encoding bytes to message: %r" % value) from exc

    if not isinstance(value, bytes):
        raise EncoderException(
            "encode_bytes must receive a bytes or bytearray value: %s %r"
            % (type(value), value)
        )
    encoded_length = encode_varint(len(value))
    return encoded_length + value


def decode_bytes(buf: bytes, pos: int) -> Tuple[bytes, int]:
    """Decode a length delimited bytes array from buf"""
    length, pos = decode_varint(buf, pos)
    end = pos + length
    try:
        return buf[pos:end], end
    except IndexError as exc:
        raise DecoderException(
            (
                "Error decoding bytes. Decoded length %d is longer than bytes"
                " available %d"
            )
            % (length, len(buf) - pos)
        ) from exc


def encode_bytes_hex(value: Any) -> bytes:
    """Encode a length delimited byte array represented by a hex string"""
    try:
        return encode_bytes(binascii.unhexlify(value))
    except (TypeError, binascii.Error) as exc:
        raise EncoderException("Error encoding hex bytestring %s" % value) from exc

def decode_bytes_hex(buf: bytes, pos: int) -> Tuple[bytes, int]:
    """Decode a length delimited byte array from buf and return a hex encoded string"""
    value, pos = decode_bytes(buf, pos)
    return binascii.hexlify(value), pos


def decode_string(value: bytes, pos: int) -> Tuple[str, int]:
    """Decode a length delimited byte array as a string"""
    length, pos = decode_varint(value, pos)
    end = pos + length
    try:
        # backslash escaping isn't reversible easily
        return value[pos:end].decode("utf-8"), end
    except (TypeError, UnicodeDecodeError) as exc:
        raise DecoderException("Error decoding UTF-8 string %r" % value[pos:end]) from exc


def encode_tag(field_number: int, wire_type: int) -> bytes:
    # Not checking bounds here, should be check before
    tag_number = (field_number << 3) | wire_type
    return encode_uvarint(tag_number)


def decode_tag(buf: bytes, pos: int) -> Tuple[int, int, int]:
    tag_number, pos = decode_uvarint(buf, pos)
    field_number = tag_number >> 3
    wire_type = tag_number & 0x7
    return field_number, wire_type, pos