# pytypes.py
from typing import Any, Dict, List, TypedDict, Union
# We say messages can have any value
# Functions we define may have fixed types, but someone could add a type
# function that outputs any arbitrary object
Message = Dict[Union[str, int], Any]

TypeDefDict = Dict[str, "FieldDefDict"]

FieldDefDict = TypedDict(
    "FieldDefDict",
    {
        "name": str,
        "type": str,
        "message_type_name": str,
        "message_typedef": TypeDefDict,
        "alt_typedefs": Dict[str, str | TypeDefDict],
        "example_value_ignored": Any,
        "seen_repeated": bool,
        "field_order": List[str],
    },
    total=False,
)