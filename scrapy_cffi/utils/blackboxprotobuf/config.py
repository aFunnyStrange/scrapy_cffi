# config.py
from .schema import WIRE_TYPE_DEFAULTS
from .exceptions import DecoderException
from typing import TYPE_CHECKING, Dict
if TYPE_CHECKING:
    from .pytypes import TypeDefDict

class Config:
    def __init__(self):
        # Map of message type names to typedefs, previously stored at
        # `blackboxprotobuf.known_messages`
        self.known_types: Dict[str, "TypeDefDict"] = {}

        # Default type for "bytes" like objects that aren't messages or strings
        # Other option is currently just 'bytes_hex'
        self.default_binary_type = "bytes"

        # Change the default type for a wiretype (eg. change ints to be signed
        # by default or fixed fields to always be float)
        self.default_types: Dict[int, str] = {}

        # Configure whether bbpb should try to re-encode fields in the same
        # order they decoded
        # Field order shouldn't matter for real protobufs, but is there to ensure
        # that bytes/string are accidentally valid protobufs don't get scrambled
        # by decoding/re-encoding
        self.preserve_field_order = True

    def get_default_type(self, wiretype: int) -> str:
        default_type = self.default_types.get(wiretype, None)
        if default_type is None:
            default_type = WIRE_TYPE_DEFAULTS.get(wiretype, None)

        if default_type is None:
            raise DecoderException(
                "Could not find default type for wire type %d" % wiretype
            )
        return default_type


default = Config()
