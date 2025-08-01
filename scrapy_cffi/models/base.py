from pydantic import BaseModel, ConfigDict, field_validator
import codecs
from pydantic_core.core_schema import FieldValidationInfo

def create_validated_model(extra_mode: str):
    class _ValidatedModel(BaseModel):
        model_config = ConfigDict(
            extra=extra_mode,
            validate_assignment=True,
            arbitrary_types_allowed=True
        )

        @field_validator("*", mode="before")
        @classmethod
        def check_special_fields(cls, v, info: FieldValidationInfo):
            if getattr(cls, "_encoding_fields", []) and info.field_name in cls._encoding_fields:
                if v is not None:
                    try:
                        codecs.lookup(v)
                    except LookupError:
                        raise ValueError(f"{info.field_name} got invalid encoding: {v}")
            if getattr(cls, "_path_fields", []) and info.field_name in cls._path_fields:
                if not isinstance(v, str) or not v.strip():
                    raise ValueError(f"{info.field_name} should be a non-empty string path")
            return v
    _ValidatedModel.__name__ = f"ValidatedModel_extra_{extra_mode}"
    return _ValidatedModel

BaseValidatedModel = create_validated_model("allow")
StrictValidatedModel = create_validated_model("ignore")

__all__ = [
    "BaseValidatedModel",
    "StrictValidatedModel",
]