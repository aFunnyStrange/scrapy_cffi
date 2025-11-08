# models.py
from enum import Enum

class BaseWireTypes(int, Enum):
    VARINT = 0
    FIXED64 = 1
    LENGTH_DELIMITED = 2
    START_GROUP = 3
    END_GROUP = 4
    FIXED32 = 5

class VarInt(int, Enum):
    MAX_UVARINT = (1 << 64) - 1
    MIN_UVARINT = 0
    MAX_SVARINT = (1 << 63) - 1
    MIN_SVARINT = -(1 << 63)

class WireTypes(int, Enum):
    uint = BaseWireTypes.VARINT
    int = BaseWireTypes.VARINT
    sint = BaseWireTypes.VARINT
    fixed32 = BaseWireTypes.FIXED32
    sfixed32 = BaseWireTypes.FIXED32
    float = BaseWireTypes.FIXED32
    fixed64 = BaseWireTypes.FIXED64
    sfixed64 = BaseWireTypes.FIXED64
    double = BaseWireTypes.FIXED64
    bytes = BaseWireTypes.LENGTH_DELIMITED
    bytes_hex = BaseWireTypes.LENGTH_DELIMITED
    string = BaseWireTypes.LENGTH_DELIMITED
    message = BaseWireTypes.LENGTH_DELIMITED
    group = BaseWireTypes.START_GROUP
    packed_uint = BaseWireTypes.LENGTH_DELIMITED
    packed_int = BaseWireTypes.LENGTH_DELIMITED
    packed_sint = BaseWireTypes.LENGTH_DELIMITED
    packed_fixed32 = BaseWireTypes.LENGTH_DELIMITED
    packed_sfixed32 = BaseWireTypes.LENGTH_DELIMITED
    packed_float = BaseWireTypes.LENGTH_DELIMITED
    packed_fixed64 = BaseWireTypes.LENGTH_DELIMITED
    packed_sfixed64 = BaseWireTypes.LENGTH_DELIMITED
    packed_double = BaseWireTypes.LENGTH_DELIMITED

WIRE_TYPE_DEFAULTS = {
    BaseWireTypes.VARINT: "int",
    BaseWireTypes.FIXED32: "fixed32",
    BaseWireTypes.FIXED64: "fixed64",
    BaseWireTypes.LENGTH_DELIMITED: None,
    BaseWireTypes.START_GROUP: None,
    BaseWireTypes.END_GROUP: None,
} 
