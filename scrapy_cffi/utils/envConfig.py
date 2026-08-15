"""Read and write readable dotenv configuration for typed settings models."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Type, TypeVar, Union

from dotenv import dotenv_values
from pydantic import BaseModel

try:
    from ..models.api import ComponentInfo
except ImportError:
    from scrapy_cffi.models.api import ComponentInfo


SettingsModel = TypeVar("SettingsModel")
PathValue = Union[str, Path]
ENV_PREFIX = "SCRAPY_CFFI_"
ENV_NESTED_DELIMITER = "__"

_COMPONENT_FIELDS = {
    "SPIDER_INTERCEPTORS_PATH",
    "DOWNLOAD_INTERCEPTORS_PATH",
    "ITEM_PIPELINES_PATH",
    "EXTENSIONS_PATH",
}


def _class_path(value: type) -> str:
    """Return a stable dotted path for a configured class."""
    return "%s.%s" % (value.__module__, value.__qualname__)


def _structured_value(value: Any) -> Any:
    """Convert settings values into JSON-compatible Python values."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, type):
        return _class_path(value)
    if isinstance(value, Mapping):
        return {
            str(_structured_value(key)): _structured_value(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, (list, tuple, set)):
        return [_structured_value(item) for item in value]
    if isinstance(value, BaseModel):
        return _structured_value(value.model_dump(mode="python"))
    enum_value = getattr(value, "value", value)
    if enum_value is not value:
        return _structured_value(enum_value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("Type %s is not configuration serializable" % type(value))


def _model_data(obj: Any) -> Dict[str, Any]:
    """Extract public configuration fields without losing class objects."""
    if isinstance(obj, BaseModel):
        data: Dict[str, Any] = {}
        for key in type(obj).model_fields:
            value = getattr(obj, key)
            if isinstance(value, BaseModel) and not isinstance(value, ComponentInfo):
                data[key] = _model_data(value)
            else:
                data[key] = value
        if obj.model_extra:
            data.update(obj.model_extra)
        return data
    return {
        key: value
        for key, value in vars(obj).items()
        if not key.startswith("_")
    }


def _dotenv_quote(value: str) -> str:
    """Quote a scalar or multiline value using python-dotenv syntax."""
    return "'%s'" % value.replace("\\", "\\\\").replace("'", "\\'")


def _dotenv_value(value: Any) -> str:
    """Render one value without discarding its scalar type."""
    serialized = _structured_value(value)
    if isinstance(serialized, (dict, list)):
        pretty_json = json.dumps(serialized, ensure_ascii=False, indent=2)
        return _dotenv_quote(pretty_json)
    if isinstance(serialized, bool):
        return str(serialized).lower()
    if isinstance(serialized, (int, float)):
        return str(serialized)
    return _dotenv_quote(str(serialized))


def _append_env_field(lines: list[str], key: str, value: Any) -> None:
    """Flatten nested Pydantic models while retaining ordinary JSON mappings."""
    if isinstance(value, BaseModel) and key not in _COMPONENT_FIELDS:
        for child_key, child_value in value.__dict__.items():
            if not child_key.startswith("_") and child_value is not None:
                _append_env_field(
                    lines,
                    "%s%s%s" % (key, ENV_NESTED_DELIMITER, child_key),
                    child_value,
                )
        return
    if key in _COMPONENT_FIELDS and isinstance(value, ComponentInfo):
        value = value.value
    lines.append("%s=%s" % (key, _dotenv_value(value)))


def _parse_env_value(value: str) -> Any:
    """Parse JSON-compatible dotenv values while preserving normal strings."""
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped.startswith(("{", "[")):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
    if stripped == "null":
        return None
    return stripped


def _deep_merge(base: Dict[str, Any], overlay: Mapping[str, Any]) -> None:
    """Merge nested configuration mappings in place."""
    for key, value in overlay.items():
        current = base.get(key)
        if isinstance(current, dict) and isinstance(value, Mapping):
            _deep_merge(current, value)
        else:
            base[key] = value


def _set_nested(target: Dict[str, Any], keys: list[str], value: Any) -> None:
    """Assign one delimiter-separated environment override."""
    current = target
    for key in keys[:-1]:
        nested = current.get(key)
        if not isinstance(nested, dict):
            nested = {}
            current[key] = nested
        current = nested
    current[keys[-1]] = value


def _environment_overlay(
    values: Mapping[str, Optional[str]],
    *,
    prefix: str,
    accept_legacy_names: bool,
    allowed_roots: Optional[set[str]] = None,
) -> Dict[str, Any]:
    """Translate flat environment variables into nested settings values."""
    overlay: Dict[str, Any] = {}
    for raw_key, raw_value in values.items():
        if raw_value is None:
            continue
        key = raw_key
        if raw_key.startswith(prefix):
            key = raw_key[len(prefix):]
        elif not accept_legacy_names:
            continue
        if not key or not key[0].isalpha():
            continue
        path = [part.upper() for part in key.split(ENV_NESTED_DELIMITER) if part]
        if path and (allowed_roots is None or path[0] in allowed_roots):
            _set_nested(overlay, path, _parse_env_value(raw_value))
    return overlay


def settings_to_env(obj: Any, env_path: PathValue) -> None:
    """Write settings as readable, typed, and nested dotenv values.

    Nested Pydantic models use ``__`` keys. Lists and ordinary dictionaries use
    indented multiline JSON supported by python-dotenv. The loader continues to
    accept the historical compact JSON representation.
    """
    lines = [
        "# Generated by scrapy_cffi; nested model fields use a double underscore."
    ]
    for key, value in vars(obj).items():
        if not key.startswith("_") and value is not None:
            if isinstance(value, BaseModel) and lines[-1] != "":
                lines.append("")
            _append_env_field(lines, key, value)

    path = Path(env_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_env_settings(
    defaults: SettingsModel,
    *,
    env_path: Optional[PathValue] = None,
    environ: Optional[Mapping[str, str]] = None,
    env_prefix: str = ENV_PREFIX,
) -> SettingsModel:
    """Overlay dotenv and process variables onto Python settings defaults.

    Process variables have highest precedence and require the
    ``SCRAPY_CFFI_`` prefix. Dotenv accepts both the new nested syntax and all
    historical unprefixed names and compact JSON values.
    """
    process_values = dict(os.environ if environ is None else environ)
    model_fields = set(type(defaults).model_fields)
    dotenv_data: Dict[str, Optional[str]] = {}
    if env_path is not None and Path(env_path).exists():
        dotenv_data = dict(dotenv_values(env_path, interpolate=False))

    data = _model_data(defaults)
    _deep_merge(
        data,
        _environment_overlay(
            dotenv_data,
            prefix=env_prefix,
            accept_legacy_names=True,
        ),
    )
    _deep_merge(
        data,
        _environment_overlay(
            process_values,
            prefix=env_prefix,
            accept_legacy_names=False,
            allowed_roots=model_fields,
        ),
    )
    return type(defaults).model_validate(data)


def env_to_settings(
    env_path: PathValue,
    cls: Type[SettingsModel],
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> SettingsModel:
    """Construct validated settings from one dotenv file and environment."""
    return load_env_settings(cls(), env_path=env_path, environ=environ)


__all__ = [
    "ENV_NESTED_DELIMITER",
    "ENV_PREFIX",
    "env_to_settings",
    "load_env_settings",
    "settings_to_env",
]
