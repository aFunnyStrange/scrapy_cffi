"""Verify readable dotenv settings and backwards-compatible overrides."""

from pathlib import Path
from typing import Dict

from scrapy_cffi.config import RedisMode
from scrapy_cffi.settings import SettingsInfo
from scrapy_cffi.utils.envConfig import (
    env_to_settings,
    load_env_settings,
    settings_to_env,
)


def test_settings_to_env_writes_nested_models_and_multiline_json(
    tmp_path: Path,
) -> None:
    """Round-trip readable nested settings without losing special strings."""
    settings = SettingsInfo(
        DEFAULT_HEADERS={
            "User-Agent": "运维配置",
            "X-Token": "a#b$TOKEN",
        }
    )
    settings.REDIS_INFO.SENTINELS = [
        ("redis-1", 26379),
        ("redis-2", 26379),
    ]
    env_path = tmp_path / ".env"

    settings_to_env(settings, env_path)
    content = env_path.read_text(encoding="utf-8")
    restored = env_to_settings(env_path, SettingsInfo, environ={})

    assert "REDIS_INFO__SENTINELS='[\n" in content
    assert '  "User-Agent": "运维配置"' in content
    assert "REDIS_INFO='{\"" not in content
    assert restored.DEFAULT_HEADERS == settings.DEFAULT_HEADERS
    assert restored.REDIS_INFO.SENTINELS == settings.REDIS_INFO.SENTINELS
    assert restored.REDIS_INFO.MODE == RedisMode.SENTINEL


def test_legacy_compact_json_dotenv_remains_supported(tmp_path: Path) -> None:
    """Load files produced by framework versions before nested dotenv keys."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                'DEFAULT_HEADERS={"User-Agent":"legacy"}',
                'REDIS_INFO={"URL":"redis://legacy:6379/2"}',
                "TIMEOUT=45",
            ]
        ),
        encoding="utf-8",
    )

    settings = env_to_settings(env_path, SettingsInfo, environ={})

    assert settings.DEFAULT_HEADERS == {"User-Agent": "legacy"}
    assert settings.REDIS_INFO.URL == "redis://legacy:6379/2"
    assert settings.TIMEOUT == 45


def test_process_environment_overrides_dotenv_and_python_defaults(
    tmp_path: Path,
) -> None:
    """Apply the documented process, dotenv, and Python precedence."""
    defaults = SettingsInfo(TIMEOUT=10)
    defaults.REDIS_INFO.URL = "redis://python:6379/0"
    env_path = tmp_path / ".env"
    env_path.write_text(
        "TIMEOUT=20\nREDIS_INFO__URL='redis://dotenv:6379/0'\n",
        encoding="utf-8",
    )
    process_values: Dict[str, str] = {
        "SCRAPY_CFFI_TIMEOUT": "30",
        "SCRAPY_CFFI_REDIS_INFO__URL": "redis://process:6379/0",
        "SCRAPY_CFFI_REDIS_INFO__PASSWORD": "123456",
        "SCRAPY_CFFI_VERIFY_HOLD_OPEN": "1",
    }

    settings = load_env_settings(
        defaults,
        env_path=env_path,
        environ=process_values,
    )

    assert settings.TIMEOUT == 30
    assert settings.REDIS_INFO.URL == "redis://process:6379/0"
    assert settings.REDIS_INFO.PASSWORD == "123456"
    assert "SCRAPY_CFFI_VERIFY_HOLD_OPEN" not in settings.model_extra
