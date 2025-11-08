# type_maps.py
from ..utils import wire, fixed
from ..exceptions import DecoderException
from typing import Any, Callable, Dict, Tuple, List

def generate_packed_encoder(wrapped_encoder: Callable[[Any], bytes]) -> Callable[[List[Any]], bytes]:
    """Generate an encoder for a packed type based on a base type encoder"""

    def length_wrapper(values: List[Any]) -> bytes:
        # Encode repeat values and prefix with the length
        output = bytearray()
        for value in values:
            output += wrapped_encoder(value)
        length = wire.encode_varint(len(output))
        return length + output

    return length_wrapper

def generate_packed_decoder(wrapped_decoder: Callable[[bytes, int], Tuple[Any, int]]) -> Callable[[bytes, int], Tuple[List[Any], int]]:
    """Generate an decoder for a packed type based on a base type decoder"""

    def length_wrapper(buf: bytes, pos: int) -> Tuple[List[Any], int]:
        # Decode repeat values prefixed with the length
        length, pos = wire.decode_varint(buf, pos)
        end = pos + length
        output = []
        while pos < end:
            value, pos = wrapped_decoder(buf, pos)
            output.append(value)
        if pos > end:
            raise DecoderException(
                (
                    "Error decoding packed field. Packed length larger than"
                    " buffer: decoded = %d, left = %d"
                )
                % (length, len(buf) - pos)
            )
        return output, pos

    return length_wrapper

# Map a blackboxprotobuf type to specific encoder
ENCODERS: Dict[str, Callable[[Any], bytes]] = {
    "uint": wire.encode_uvarint,
    "int": wire.encode_varint,
    "sint": wire.encode_svarint,
    "fixed32": fixed.encode_fixed32,
    "sfixed32": fixed.encode_sfixed32,
    "float": fixed.encode_float,
    "fixed64": fixed.encode_fixed64,
    "sfixed64": fixed.encode_sfixed64,
    "double": fixed.encode_double,
    "bytes": wire.encode_bytes,
    "bytes_hex": wire.encode_bytes_hex,
    "string": wire.encode_string,
    "packed_uint": generate_packed_encoder(wire.encode_uvarint),
    "packed_int": generate_packed_encoder(wire.encode_varint),
    "packed_sint": generate_packed_encoder(wire.encode_svarint),
    "packed_fixed32": generate_packed_encoder(fixed.encode_fixed32),
    "packed_sfixed32": generate_packed_encoder(fixed.encode_sfixed32),
    "packed_float": generate_packed_encoder(fixed.encode_float),
    "packed_fixed64": generate_packed_encoder(fixed.encode_fixed64),
    "packed_sfixed64": generate_packed_encoder(fixed.encode_sfixed64),
    "packed_double": generate_packed_encoder(fixed.encode_double),
}

# Map a blackboxprotobuf type to specific decoder
DECODERS: Dict[str, Callable[[bytes, int], Tuple[Any, int]]] = {
    "uint": wire.decode_uvarint,
    "int": wire.decode_varint,
    "sint": wire.decode_svarint,
    "fixed32": fixed.decode_fixed32,
    "sfixed32": fixed.decode_sfixed32,
    "float": fixed.decode_float,
    "fixed64": fixed.decode_fixed64,
    "sfixed64": fixed.decode_sfixed64,
    "double": fixed.decode_double,
    "bytes": wire.decode_bytes,
    "bytes_hex": wire.decode_bytes_hex,
    "string": wire.decode_string,
    "packed_uint": generate_packed_decoder(wire.decode_uvarint),
    "packed_int": generate_packed_decoder(wire.decode_varint),
    "packed_sint": generate_packed_decoder(wire.decode_svarint),
    "packed_fixed32": generate_packed_decoder(fixed.decode_fixed32),
    "packed_sfixed32": generate_packed_decoder(fixed.decode_sfixed32),
    "packed_float": generate_packed_decoder(fixed.decode_float),
    "packed_fixed64": generate_packed_decoder(fixed.decode_fixed64),
    "packed_sfixed64": generate_packed_decoder(fixed.decode_sfixed64),
    "packed_double": generate_packed_decoder(fixed.decode_double),
}