# length_delim.py
import logging
from .schema import BaseWireTypes, WireTypes, ENCODERS, DECODERS, TypeDef, FieldDef
from .utils import wire
from .exceptions import (
    EncoderException,
    DecoderException,
    TypedefException,
    BlackboxProtobufException,
)

from typing import Any, Callable, Dict, Tuple, Optional, List, TYPE_CHECKING, Union, Any
if TYPE_CHECKING:
    from .config import Config
    from .pytypes import Message

logger = logging.getLogger(__name__)

def encode_message(
    data: "Message", 
    config: "Config", 
    typedef: TypeDef, 
    path: Optional[List[str]]=None, 
    field_order: Optional[List[str]]=None
) -> bytes:
    """Encode a Python dictionary to a binary protobuf message"""
    output = bytearray()
    if path is None:
        path = []

    output_len = 0
    field_outputs: Dict[str, List[bytes]] = {}
    for field_id, value in data.items():
        field_number, outputs = _encode_message_field(
            config, typedef, path, field_id, value
        )

        # In case the field number is represented in multiple locations in data
        # (eg. as an int, as name, as a string with an int)
        field_outputs.setdefault(field_number, []).extend(outputs)
        output_len += len(outputs)

    if output_len > 0:
        if (
            config.preserve_field_order
            and field_order is not None
            and len(field_order) == output_len
        ):
            # check for old typedefs which had field_order as a tuple
            if isinstance(field_order[0], tuple):
                field_order = [x[0] for x in field_order]
            for field_number in field_order:
                try:
                    output += field_outputs[field_number].pop(0)
                except (IndexError, KeyError):
                    # If these don't match up despite us checking the overall
                    # length, then we probably have something weird going on
                    # with field naming.
                    # This might mean ordering is off from the original, but
                    # should break real protobuf messages
                    logger.debug(
                        "The field_order list does not match the fields from _encode_message_field"
                    )
                    # If we're hitting a mismatch between the field order and
                    # what data we have, then just bail. We can encode the rest
                    # normally
                    break

        # Group  together elements in an array
        for values in field_outputs.values():
            for value in values:
                output += value

    return output

def _encode_message_field(
    config: "Config", 
    typedef: TypeDef, 
    path: List[str], 
    field_id: Union[str, int], 
    value: Any
) -> Tuple[str, List[bytes]]:
    field_key = str(field_id)

    fielddef_results = typedef.lookup_fielddef(field_key)

    if fielddef_results is None:
        raise EncoderException(
            "Provided field name/number %s is not valid" % (field_key),
            path,
        )
    field_number, fielddef = fielddef_results

    field_path = path[:]
    field_path.append(str(field_number))

    field_type = fielddef.lookup_field_type(field_key, config, field_path)

    if field_type is None:
        raise EncoderException(
            "Provided field name/number %s / %s is not valid"
            % (field_key, field_number),
            field_path,
        )

    field_encoder: Optional[Callable[[Any], bytes]] = None
    if isinstance(field_type, TypeDef):
        field_typedef = field_type
        field_type = "message"
        field_encoder = lambda data: encode_lendelim_message(
            data,
            config,
            field_typedef,
            path=field_path,
            field_order=fielddef.field_order,
        )
    else:
        if field_type not in ENCODERS:
            raise TypedefException("Unknown type: %s" % field_type)
        field_encoder = ENCODERS[field_type]
        if field_encoder is None:
            raise TypedefException(
                "Encoder not implemented for %s" % field_type, field_path
            )

    # Encode the tag
    tag = wire.encode_tag(
        int(field_number), WireTypes[field_type].value
    )

    outputs = []
    try:
        # Repeated values we'll encode each one separately and add them to the outputs list
        # Packed values take in a list, but encode them into a single length
        # delimited field, so we handle those as a non-repeated value
        if isinstance(value, list) and not field_type.startswith("packed_"):
            for repeated in value:
                outputs.append(tag + field_encoder(repeated))
        else:
            outputs.append(tag + field_encoder(value))
            
    except EncoderException as exc:
        exc.set_path(field_path)
        raise exc.with_traceback(exc.__traceback__)

    return field_number, outputs

def decode_message(
    buf: bytes, 
    config: "Config", 
    typedef: Optional[TypeDef]=None, 
    pos: int=0, 
    end: Optional[int]=None, 
    depth: int=0, 
    path: Optional[List[str]]=None
) -> Tuple["Message", TypeDef, List[str], int]:
    """Decode a protobuf message with no length prefix"""
    if end is None:
        end = len(buf)

    if typedef is None:
        typedef = TypeDef()

    if path is None:
        path = []

    output: "Message" = {}
    seen_repeated: Dict[str, bool] = {}
    mut_typedef = typedef.make_mutable()

    grouped_fields, field_order, pos = _group_by_number(buf, pos, end, path)
    for field_number, (wire_type, buffers) in grouped_fields.items():
        # wire_type should already be validated by _group_by_number

        field_path = path[:] + [field_number]

        fielddef_pair: Optional[Tuple[str, FieldDef]] = mut_typedef.lookup_fielddef_number(field_number)

        if fielddef_pair is None:
            fielddef = FieldDef(field_number)
        else:
            fielddef = fielddef_pair[1]

        # Decode messages (which may have multiple typedefs)  or unknown length delimited fields
        if wire_type == BaseWireTypes.LENGTH_DELIMITED and not isinstance(
            fielddef.lookup_field_type_number("0", config, field_path), str
        ):
            output_map, new_fielddef = _try_decode_lendelim_fields(
                buffers, fielddef, config, field_path
            )

            # Merge length delim field into the output map
            for field_key, field_outputs in output_map.items():
                output.setdefault(field_key, []).extend(field_outputs)
            seen_repeated[fielddef.name] = new_fielddef.seen_repeated
            mut_typedef.set_fielddef(field_number, new_fielddef)
        else:
            field_outputs, new_fielddef, field_alt_type_id = _decode_standard_field(
                wire_type, buffers, fielddef, config, path
            )

            field_key = new_fielddef.field_key(field_alt_type_id)
            output.setdefault(field_key, []).extend(field_outputs)
            seen_repeated[fielddef.name] = new_fielddef.seen_repeated

            # Save the field typedef/type back to the typedef
            mut_typedef.set_fielddef(field_number, new_fielddef)

    _simplify_output(output, seen_repeated)
    return output, mut_typedef, field_order, pos

def _decode_standard_field(
    wire_type: int, 
    buffers: List[bytes], 
    fielddef: FieldDef, 
    config: "Config", 
    field_path: List[str]
) -> Tuple[List[Any], FieldDef, str]:
    field_outputs = None
    field_alt_type_id = None
    for alt_type_id, field_type in fielddef.resolve_types(config, field_path).items():
        if isinstance(field_type, TypeDef):
            # Skip message types
            continue
        if (
            not isinstance(field_type, str)
            or BaseWireTypes[field_type] != wire_type
        ):
            raise DecoderException(
                "Type %s from typedef did not match wiretype %s"
                % (field_type, wire_type),
                path=field_path,
            )

        if field_type not in DECODERS:
            raise TypedefException(
                "Type %s does not have a decoder" % (field_type),
                path=field_path,
            )
        decoder = DECODERS[field_type]
        try:
            field_outputs = [decoder(buf, 0)[0] for buf in buffers]
            field_alt_type_id = alt_type_id
        except BlackboxProtobufException as exc:
            # Error decoding, try next one if we have one
            continue
        # Decoding worked
        break

    if field_outputs is None:
        field_type = config.get_default_type(wire_type)
        default_decoder = DECODERS[field_type]

        field_outputs = [default_decoder(buf, 0)[0] for buf in buffers]

    mut_fielddef = fielddef.make_mutable()
    if field_alt_type_id is None:
        field_alt_type_id = mut_fielddef.next_alt_type_id()

    mut_fielddef.set_type(field_alt_type_id, field_type)

    if field_outputs is None:
        raise DecoderException(
            "Unable to decode wire_type %s" % (wire_type),
            path=field_path,
        )
    if isinstance(field_type, str) and field_type.startswith("packed_"):
        # Packed decoding will return a list of lists
        field_outputs = [y for x in field_outputs for y in x]
        mut_fielddef.mark_repeated()
    # Mark repeated if we have have more than one
    # Don't need to worry if it's already repeated
    elif len(field_outputs) > 1:
        mut_fielddef.mark_repeated()

    return field_outputs, mut_fielddef, field_alt_type_id

def _simplify_output(output: "Message", seen_repeated: Dict[str, bool]) -> None:
    # If any outputs only have one element, convert them from a list to solo
    # Mutates output
    for field_key, field_outputs in output.items():
        if isinstance(field_outputs, list) and len(field_outputs) == 1:
            field_name = (
                field_key.split("-", 1)[0]
                if isinstance(field_key, str)
                else str(field_key)
            )
            if not seen_repeated[field_name]:
                output[field_key] = field_outputs[0]

def _group_by_number(
    buf: bytes, 
    pos: int, 
    end: int, 
    path: List[str]
) -> Tuple[Dict[str, Tuple[int, List[bytes]]], List[str], int]:
    # Parse through the whole message and split into buffers based on wire
    # type and organized by field number. This forces us to parse the whole
    # message at once, but I think we're doing that anyway. This catches size
    # errors early as well, which is usually the best indicator of if it's a
    # protobuf message or not.
    # Returns a dictionary like:
    #     {
    #         "2": (<wiretype>, [<data>])
    #     }

    output_map: Dict[str, Tuple[int, List[bytes]]] = {}
    field_order = []
    while pos < end:
        # Read in a field
        field_number, wire_type, pos = wire.decode_tag(buf, pos)

        # We want field numbers as strings everywhere
        field_id = str(field_number)

        field_path = path[:] + [field_id]

        if field_id in output_map and output_map[field_id][0] != wire_type:
            # This should never happen
            raise DecoderException(
                "Field %s has mistmatched wiretypes. Previous: %s Now: %s"
                % (field_id, output_map[field_id][0], wire_type),
                path=field_path,
            )

        length = None
        if wire_type == BaseWireTypes.VARINT:
            # We actually have to read in the whole varint to figure out it's size
            _, new_pos = wire.decode_uvarint(buf, pos)
            length = new_pos - pos
        elif wire_type == BaseWireTypes.FIXED32:
            length = 4
        elif wire_type == BaseWireTypes.FIXED64:
            length = 8
        elif wire_type == BaseWireTypes.LENGTH_DELIMITED:
            # Read the length from the start of the message
            # add on the length of the length tag as well
            bytes_length, new_pos = wire.decode_varint(buf, pos)
            length = bytes_length + (new_pos - pos)
        elif wire_type in [
            BaseWireTypes.START_GROUP,
            BaseWireTypes.END_GROUP,
        ]:
            raise DecoderException("GROUP wire types not supported", path=field_path)
        else:
            raise DecoderException(
                "Got unknown wire type: %d" % wire_type, path=field_path
            )
        if pos + length > end:
            raise DecoderException(
                "Decoded length for field %s goes over end: %d > %d"
                % (field_id, pos + length, end),
                path=field_path,
            )

        field_buf = buf[pos : pos + length]

        if field_id in output_map:
            output_map[field_id][1].append(field_buf)
        else:
            output_map[field_id] = (wire_type, [field_buf])
        field_order.append(field_id)
        pos += length
    return output_map, field_order, pos

def _try_decode_lendelim_fields(
    buffers: List[bytes], 
    fielddef: FieldDef, 
    config: "Config", 
    path: List[str]
) -> Tuple["Message", FieldDef]:
    # Mutates message_output

    # This is where things get weird
    # To start, since we want to decode messages and not treat every
    # embedded message as bytes, we have to guess if it's a message or
    # not.
    # Unlike other types, we can't assume our message types are
    # consistent across the tree or even within the same message.
    # A field could be a bytes type that that decodes to multiple different
    # messages that don't have the same type definition. This is where
    # 'alt_typedefs' let us say that these are the different message types
    # we've seen for this one field.
    # In general, if something decodes as a message once, the rest should too
    # and we can enforce that across a single message, but not multiple
    # messages.
    # This is going to change the definition of "alt_typedefs" a bit from just
    # alternate message type definitions to also allowing downgrading to
    # 'bytes' or string with an 'alt_type' if it doesn't parse

    message_output: "Message" = {}

    # TODO potential performance improvement: Do a first pass with {} or just group by number and use the results to validate if it's even valid protobuf and quick match wire_types against typedefs
    try:
        outputs_map: Dict[str, Any] = {}
        field_order: List[str] = [] 

        next_alt_type_id = int(fielddef.next_alt_type_id())
        field_types = fielddef.resolve_types(config, path)

        # We don't want any mutable changes within this loop, we want
        # everything to rollback if it fails
        for buf in buffers:
            output = None
            output_typedef = None
            output_typedef_num = None
            new_field_order: List[str] = []

            for alt_type_id, field_type in sorted(
                field_types.items(), key=lambda x: int(x[0])
            ):
                # Skip non message types
                if not isinstance(field_type, TypeDef):
                    continue

                try:
                    (
                        output,
                        output_typedef,
                        new_field_order,
                        _,
                    ) = decode_lendelim_message(buf, config, field_type)
                except Exception as exc:
                    # If we get an exception, then this isn't the right typedef, try the next
                    continue

                output_typedef_num = alt_type_id
                # If we didn't get an exception, then we found the right type
                break
            # If we didn't find a type above, then try an anonymous type
            # If this fails, we fall back to string and bytes for all types
            if output is None:
                output, output_typedef, new_field_order, _ = decode_lendelim_message(
                    buf, config, None
                )
                output_typedef_num = str(next_alt_type_id)
                next_alt_type_id += 1

            if output_typedef is None or output_typedef_num is None:
                raise DecoderException(
                    "Could not find an output_typedef or output_typedef_num. This should not happen under any circumstances."
                )

            # save the output or typedef we found
            field_types[output_typedef_num] = output_typedef
            outputs_map.setdefault(output_typedef_num, []).append(output)

            # we should technically have a different field order for each instance of the data
            # but that would require a very messy JSON which we're trying to avoid
            if len(new_field_order) > len(field_order):
                field_order = new_field_order

        # was able to decode everything as a message
        mut_fielddef = fielddef.make_mutable()
        mut_fielddef.set_types(field_types)

        if config.preserve_field_order:
            mut_fielddef.set_field_order(field_order)

        # messages get set as "key-alt_number"
        for output_typedef_num, outputs in outputs_map.items():
            output_field_key = mut_fielddef.field_key(output_typedef_num)

            message_output[output_field_key] = outputs
            if len(outputs) > 1:
                mut_fielddef.mark_repeated()

        # success, return
        return message_output, mut_fielddef
    except DecoderException as exc:
        # this should be pretty common, don't be noisy or throw an exception
        logger.debug(
            "Could not decode a buffer for field (%s) as a message: %s",
            path,
            exc,
        )

    # Decoding as a message did not work, try strings and then the configured binary type
    # By default, default_binary_type will be redundant with bytes, but we want
    # to fall back on bytes if default_binary_type fails for any reason
    for target_type in ["string", config.default_binary_type, "bytes"]:
        try:
            outputs = []
            decoder = DECODERS[target_type]
            for buf in buffers:
                output, _ = decoder(buf, 0)
                outputs.append(output)

            field_alt_type_id = None
            # check if the type is already known
            field_types = fielddef.resolve_types(config, path)
            for alt_type_id, field_type in field_types.items():
                if field_type == target_type:
                    field_alt_type_id = alt_type_id
                    break

            mut_fielddef = fielddef.make_mutable()
            if field_alt_type_id is None:
                field_alt_type_id = mut_fielddef.add_type(target_type)

            field_key: str = mut_fielddef.field_key(field_alt_type_id)
            
            message_output[field_key] = outputs
            return message_output, mut_fielddef
        except DecoderException:
            continue

    # This should never happen, we should always be able to use bytes
    raise DecoderException("Unable to decode field with typedef", path=path)

def encode_lendelim_message(
    data: "Message", 
    config: "Config", 
    typedef: TypeDef, 
    path: Optional[List[str]]=None, 
    field_order: Optional[List[str]]=None
) -> bytes:
    """Encode data as a length delimited protobuf message"""
    message_out = encode_message(
        data, config, typedef, path=path, field_order=field_order
    )
    length = wire.encode_varint(len(message_out))
    return length + message_out


def decode_lendelim_message(
    buf: bytes, 
    config: "Config", 
    typedef: Optional[TypeDef]=None, 
    pos: int=0, 
    depth: int=0, 
    path: Optional[List[str]]=None
) -> Tuple["Message", TypeDef, List[str], int]:
    """Deocde a length delimited protobuf message from buf"""
    length, pos = wire.decode_varint(buf, pos)
    ret = decode_message(
        buf, config, typedef, pos, pos + length, depth=depth, path=path
    )
    return ret