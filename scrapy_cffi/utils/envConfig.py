import json
from pathlib import Path
from dotenv import dotenv_values
from typing import Type, Any, Union
try:
    from ..models.api import ComponentInfo
except BaseException as e:
    from scrapy_cffi.models.api import ComponentInfo

def _json_serialize(value: Any):
    """Convert non-serializable objects into serializable format for JSON."""
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Type {type(value)} not JSON serializable")

# Fields that require special handling as ComponentInfo objects
_COMPONENT_FIELDS = [
    "SPIDER_INTERCEPTORS_PATH",
    "DOWNLOAD_INTERCEPTORS_PATH",
    "ITEM_PIPELINES_PATH",
    "EXTENSIONS_PATH",
]

def settings_to_env(obj: Any, env_path: Union[str, Path]):
    """
    Convert a Python object (Pydantic model or plain object) into a .env file.
    - dict/list fields are serialized as JSON
    - bool fields are converted to 'true'/'false'
    - ComponentInfo fields are written as empty JSON '{}'
    - Fields with None values are skipped
    """
    lines = []

    data = getattr(obj, "model_dump", None)
    if callable(data):
        data = obj.model_dump()
    else:
        data = obj.__dict__

    for key, value in data.items():
        if key.startswith("_") or value is None:
            continue
        # Write ComponentInfo fields as empty JSON
        if key in _COMPONENT_FIELDS:
            value_str = "{}"
        elif isinstance(value, (dict, list)):
            value_str = json.dumps(value, ensure_ascii=False, default=_json_serialize)
        elif isinstance(value, bool):
            value_str = str(value).lower()
        else:
            value_str = str(value)
        lines.append(f"{key}={value_str}")

    env_path = Path(env_path)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines), encoding="utf-8")


def env_to_settings(env_path: Union[str, Path], cls: Type[Any]) -> Any:
    """
    Load data from a .env file and convert it into an instance of the specified class.
    - Automatically parses JSON strings into dict/list
    - Converts 'true'/'false' to bool, numbers to int/float
    - Restores ComponentInfo fields from dict to ComponentInfo objects
    """
    raw_env = dotenv_values(env_path)
    processed = {}

    for k, v in raw_env.items():
        if v is None:
            continue
        v_strip = v.strip()
        # JSON object or list
        if (v_strip.startswith("{") and v_strip.endswith("}")) or \
           (v_strip.startswith("[") and v_strip.endswith("]")):
            try:
                processed[k] = json.loads(v_strip)
                continue
            except json.JSONDecodeError:
                pass
        # Boolean
        if v_strip.lower() in {"true", "false"}:
            processed[k] = v_strip.lower() == "true"
        # Float or int
        elif v_strip.replace('.', '', 1).replace('-', '', 1).isdigit():
            if '.' in v_strip:
                processed[k] = float(v_strip)
            else:
                processed[k] = int(v_strip)
        else:
            processed[k] = v_strip

    # Restore ComponentInfo fields
    for f in _COMPONENT_FIELDS:
        if f in processed and isinstance(processed[f], dict):
            processed[f] = ComponentInfo.from_raw(processed[f], f)

    return cls(**processed)

__all__ = [
    "settings_to_env",
    "env_to_settings"
]

if __name__ == "__main__":
    from scrapy_cffi.settings import SettingsInfo

    config = SettingsInfo()
    config.TEST_DATA = {"a":1, "b":2}
    print("Before .env:", config.TEST_DATA)

    env_path = r"D:\_project\use_scrapy\cffi_project\.env.dev"

    # Generate .env
    settings_to_env(config, env_path)

    # Load from .env during deployment
    config2 = env_to_settings(env_path, SettingsInfo)
    print("After .env:", config2.TEST_DATA)
