# api.py
from . import length_delim
from .schema import TypeDef
from .config import default as default_config
from .exceptions import (
    DecoderException,
    EncoderException
)
from typing import Union, Tuple, Optional, TYPE_CHECKING

# Circular imports on Config if we don't check here
if TYPE_CHECKING:
    from .pytypes import Message, TypeDefDict
    from .config import Config

def decode_message(
    buf: bytes, 
    message_type: Optional[Union[str, "TypeDefDict"]]=None, 
    config: Optional["Config"]=None
) -> Tuple["Message", "TypeDefDict"]:
    """Decode a protobuf message and return a python dictionary representing
    the message.

    Args:
        buf: Bytes representing an encoded protobuf message
        message_type: Optional type to use as the base for decoding. Allows for
            customizing field types or names. Can be a python dictionary or a
            message type name which maps to the `known_types` dictionary in the
            config. Defaults to an empty definition '{}'.
        config: `.config.Config` object which allows
            customizing default types for wire types and holds the
            `known_types` array. Defaults to
            `.config.default` if not provided.
    Returns:
        A tuple containing a python dictionary representing the message and a
        type definition for re-encoding the message.

        The type definition is based on the `message_type` argument if one was
        provided, but may add additional fields if new fields were encountered
        during decoding.
    """

    if config is None:
        config = default_config

    if isinstance(buf, bytearray):
        buf = bytes(buf)
    elif isinstance(buf, str):
        buf = buf.encode("utf-8")
    
    if not isinstance(buf, bytes):
        raise TypeError("not expecting type '%s'" % type(buf))

    if message_type is None:
        message_type = {}
    elif isinstance(message_type, str):
        message_type = config.known_types.get(message_type, {})

    if not isinstance(message_type, dict):
        raise DecoderException("Decode message received an invalid typedef type. Typedef should be a string with a message name, a dictionary, or None")
    
    value, typedef, _, _ = length_delim.decode_message(
        buf, config, TypeDef.from_dict(message_type)
    )
    return value, typedef.to_dict()


def encode_message(
    value: "Message", 
    message_type: Union[str, "TypeDefDict"], 
    config: Optional["Config"]=None
) -> bytes:
    """Re-encode a python dictionary as a binary protobuf message.

    Args:
        value: Python dictionary to re-encode to bytes. This should usually be
            a modified version of the dictionary returned by `decode_message`.
        message_type: Type definition to use to re-encode the message. This
            will should generally be the type definition returned from the
            original `decode_message` call.
        config: `.config.Config` object which allows
            customizing default types for wire types and holds the
            `known_types` array. Defaults to
            `.config.default` if not provided.
    Returns:
        A bytearray containing the encoded protobuf message.
    """

    if config is None:
        config = default_config

    if message_type is None:
        raise EncoderException(
            "Encode message must have valid type definition. message_type cannot be None"
        )

    if isinstance(message_type, str):
        if message_type not in config.known_types:
            raise EncoderException(
                "The provided message type name (%s) is not known. Encoding requires a valid type definition"
                % message_type
            )
        message_type = config.known_types[message_type]

    if not isinstance(message_type, dict):
        raise EncoderException(
            "Encode message received an invalid typedef type. Typedef should be a string with a message name or a dictionary."
        )
    return bytes(
        length_delim.encode_message(
            value, config, TypeDef.from_dict(message_type)
        )
    )