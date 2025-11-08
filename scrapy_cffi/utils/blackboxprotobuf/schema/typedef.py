# typedef.py
from ..exceptions import TypedefException
from typing import TYPE_CHECKING, Dict, Optional, Any, List, Tuple, Union
if TYPE_CHECKING:
    from ..config import Config
    from ..pytypes import TypeDefDict, FieldDefDict


class TypeDef(object):
    def __init__(self):
        self._fields: Dict[str, "FieldDef"] = {}
        self._field_names: Dict[str, str] = {}

    @staticmethod
    def from_dict(typedef_dict: "TypeDefDict") -> "TypeDef":
        typedef = TypeDef()
        for field_id, fielddef_dict in typedef_dict.items():
            fielddef = FieldDef.from_dict(fielddef_dict, field_id)
            typedef._fields[field_id] = fielddef
            if fielddef._name:
                typedef._field_names[fielddef._name] = field_id
        return typedef

    def to_dict(self) -> "TypeDefDict":
        return {field: fielddef.to_dict() for field, fielddef in self._fields.items()}

    def make_mutable(self) -> "MutableTypeDef":
        mutable = MutableTypeDef()
        # Copy fields but don't deep copy
        # They should get immutable copies of FieldDef
        mutable._fields = self._fields.copy()
        return mutable

    def lookup_fielddef(self, key: str) -> Optional[Tuple[str, "FieldDef"]]:
        """Look up a field definition by number (w/ alt typedef) or name"""
        # We don't care what the alt number is now
        field_name = key.split("-", 1)[0]

        field_id = self._field_names.get(field_name, field_name)

        if field_id in self._fields:
            return field_id, self._fields[field_id]

        return None

    def lookup_fielddef_number(self, field_id: str) -> Optional[Tuple[str, "FieldDef"]]:
        if field_id in self._fields:
            return field_id, self._fields[field_id]
        return None

class MutableTypeDef(TypeDef):
    def set_fielddef(self, field_number: str, fielddef: "FieldDef") -> None:
        self._fields[field_number] = fielddef
        if fielddef._name:
            self._field_names[fielddef._name] = field_number

class FieldDef(object):
    def __init__(self, field_id: str) -> None:
        self._name: Optional[str] = None
        self._field_id: str = field_id
        self._message_type_name: Optional[str] = None
        # Normal type will be 0, alts starting at 1
        # Each field will have either the type or a typedef
        # We don't allow message_type_name in alt_typedefs, we'll use it for any "message" entry instead
        self._types: Dict[str, Union[str, "TypeDef"]] = {}
        self._example_value: Any = None
        self._seen_repeated: bool = False
        self._field_order: Optional[List[str]] = None

    @staticmethod
    def from_dict(fielddef_dict: "FieldDefDict", field_id: str) -> "FieldDef":
        fielddef = FieldDef(field_id)

        if "name" in fielddef_dict:
            fielddef._name = fielddef_dict["name"]

        if "type" in fielddef_dict:
            field_type = fielddef_dict["type"]

            if field_type == "message" and "message_typedef" in fielddef_dict:
                fielddef._types["0"] = TypeDef.from_dict(
                    fielddef_dict["message_typedef"]
                )
            else:
                fielddef._types["0"] = field_type

        if "message_type_name" in fielddef_dict:
            # We could lookup the typedef, but better to wait to resolve
            fielddef._message_type_name = fielddef_dict["message_type_name"]

        if "alt_typedefs" in fielddef_dict:
            for alt_number, alt_typedef in fielddef_dict["alt_typedefs"].items():
                if isinstance(alt_typedef, dict):
                    fielddef._types[alt_number] = TypeDef.from_dict(alt_typedef)
                else:
                    fielddef._types[alt_number] = alt_typedef

        if "example_value_ignored" in fielddef_dict:
            fielddef._example_value = fielddef_dict["example_value_ignored"]

        if "seen_repeated" in fielddef_dict:
            fielddef._seen_repeated = fielddef_dict["seen_repeated"]

        if "field_order" in fielddef_dict:
            fielddef._field_order = fielddef_dict["field_order"]

        return fielddef

    def to_dict(self) -> "FieldDefDict":
        fielddef_dict: "FieldDefDict" = {}
        if self._name:
            fielddef_dict["name"] = self._name
        if self._message_type_name:
            fielddef_dict["message_type_name"] = self._message_type_name
        if self._example_value:
            fielddef_dict["example_value_ignored"] = self._example_value
        if self._seen_repeated:
            fielddef_dict["seen_repeated"] = self._seen_repeated
        if self._field_order:
            fielddef_dict["field_order"] = self._field_order

        field_type = self._types.get("0")
        if isinstance(field_type, TypeDef):
            field_typedef = field_type.to_dict()
            field_type = "message"
            fielddef_dict["message_typedef"] = field_typedef

        if field_type:
            fielddef_dict["type"] = field_type

        if field_type and len(self._types) > 1:
            fielddef_dict["alt_typedefs"] = {
                alt_num: (
                    alt_type.to_dict() if isinstance(alt_type, TypeDef) else alt_type
                )
                for alt_num, alt_type in self._types.items()
                if alt_num != "0"
            }

        return fielddef_dict

    def make_mutable(self) -> "MutableFieldDef":
        mutable = MutableFieldDef(self._field_id)
        mutable._name = self._name
        mutable._message_type_name = self._message_type_name
        mutable._types = self._types.copy()
        mutable._example_value = self._example_value
        mutable._seen_repeated = self._seen_repeated
        mutable._field_order = self._field_order
        return mutable

    def lookup_field_type(self, key: str, config: "Config", field_path: List[str]) -> Optional[Union[str, "TypeDef"]]:
        if "-" in key:
            alt_type_id = key.split("-", 1)[1]
        else:
            alt_type_id = "0"

        return self.lookup_field_type_number(alt_type_id, config, field_path)

    # Lookup fieled type by just alt type number
    def lookup_field_type_number(self, alt_type_id: str, config: "Config", field_path: List[str]) -> Optional[Union[str, "TypeDef"]]:

        if alt_type_id not in self._types:
            return None

        field_type = self._types[alt_type_id]
        if field_type == "message":
            # We have to look up the message type name
            return self.resolve_message_type_name(config, field_path)

        return field_type

    @property
    def name(self) -> str:
        if self._name:
            return self._name
        return self._field_id

    def field_key(self, alt_field_id: str) -> str:
        if alt_field_id == "0":
            return self.name
        else:
            return self.name + "-" + alt_field_id

    def next_alt_type_id(self) -> str:
        existing_ids = [int(alt_type_id) for alt_type_id in self._types.keys()]
        if len(existing_ids) == 0:
            return "0"
        else:
            return str(max(existing_ids) + 1)

    @property
    def field_order(self) -> Optional[List[str]]:
        # someone could mutate the list returned, but that's not a high
        # priority
        return self._field_order

    @property
    def seen_repeated(self) -> bool:
        return self._seen_repeated

    def resolve_message_type_name(self, config: "Config", field_path: List[str]) -> "TypeDef":
        if self._message_type_name not in config.known_types:
            raise TypedefException(
                "Message name '%s' has not been defined in known types"
                % self._message_type_name,
                field_path,
            )
        return TypeDef.from_dict(config.known_types[self._message_type_name])

    def resolve_types(self, config: "Config", field_path: List[str]) -> Dict[str, Union[str, "TypeDef"]]:
        field_types = self._types.copy()
        if field_types.get("0") == "message":
            field_types["0"] = self.resolve_message_type_name(config, field_path)
        return field_types


class MutableFieldDef(FieldDef):
    def set_field_order(self, field_order: List[str]) -> None:
        self._field_order = field_order

    def mark_repeated(self) -> None:
        self._seen_repeated = True

    def set_type(self, alt_type_id: str, field_type: Union[str, "TypeDef"]) -> None:
        self._types[alt_type_id] = field_type

    def set_types(self, types: Dict[str, Union[str, "TypeDef"]]) -> None:
        self._types = types

    def add_type(self, field_type: Union[str, "TypeDef"]) -> str:
        alt_type_id = self.next_alt_type_id()
        self.set_type(alt_type_id, field_type)
        return alt_type_id
