from . import StrictValidatedModel
from ..utils import load_object
from typing import List, Type, Union, Dict, Any
from pydantic import Field

class ComponentInfo(StrictValidatedModel):
    value: List[Type] = Field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: Union[Dict[str, Any], List[Any], str, type], field_name="") -> "ComponentInfo":
        # dict -> sort by value and use key as path or class
        if isinstance(raw, dict):
            try:
                sorted_items = sorted(raw.items(), key=lambda item: item[1])
                items = [cls._load(k, field_name) for k, _ in sorted_items]
                return cls(value=items)
            except Exception:
                raise ValueError(f"{field_name}: dict values must be sortable")
        # list -> supports str or class
        elif isinstance(raw, list):
            if all(isinstance(i, (str, type)) for i in raw):
                return cls(value=[cls._load(i, field_name) for i in raw])
            raise ValueError(f"{field_name}: list elements must be str or class")
        # single str or class
        elif isinstance(raw, (str, type)):
            return cls(value=[cls._load(raw, field_name)])
        elif raw is None:
            cls(value=[])
        else:
            raise ValueError(f"{field_name}: must be dict, list[str|class], str, or class")

    @staticmethod
    def _load(obj: Union[str, type], field_name: str) -> Type:
        if isinstance(obj, type):
            return obj
        try:
            return load_object(obj)
        except Exception as e:
            raise ValueError(f"{field_name}: failed to load class from path '{obj}': {e}")
        
__all__ = [
    "ComponentInfo"
]