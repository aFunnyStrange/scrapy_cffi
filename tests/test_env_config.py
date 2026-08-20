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
        "TIMEOUT": "30",
        "REDIS_INFO__URL": "redis://process:6379/0",
        "REDIS_INFO__PASSWORD": "123456",
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


def test_direct_process_name_wins_over_legacy_prefix(tmp_path: Path) -> None:
    """Prefer Pydantic field names while keeping old process names readable."""
    settings = load_env_settings(
        SettingsInfo(),
        env_path=tmp_path / "missing.env",
        environ={
            "SCRAPY_CFFI_TIMEOUT": "10",
            "TIMEOUT": "25",
        },
    )

    assert settings.TIMEOUT == 25


def test_direct_dotenv_name_wins_over_legacy_prefix(tmp_path: Path) -> None:
    """Use the same deterministic precedence inside one dotenv file."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "TIMEOUT=25\nSCRAPY_CFFI_TIMEOUT=10\n",
        encoding="utf-8",
    )

    settings = env_to_settings(env_path, SettingsInfo, environ={})

    assert settings.TIMEOUT == 25


def test_global_task_lock_defaults_to_300_and_downloader_is_unlimited() -> None:
    """Bound total runtime work without adding a downloader-local default."""
    assert SettingsInfo().MAX_GLOBAL_CONCURRENT_TASKS == 300
    assert SettingsInfo().MAX_CONCURRENT_REQ is None
    assert SettingsInfo(MAX_CONCURRENT_REQ=None).MAX_CONCURRENT_REQ is None


def test_optional_curl_native_directory_round_trips_as_path(
    tmp_path: Path,
) -> None:
    """Load the optional runtime adapter path without activating curl_cffi."""
    native_dir = tmp_path / "native" / "windows"
    env_path = tmp_path / ".env"
    env_path.write_text(
        "CURL_CFFI_RUNTIME_DIR='%s'\n" % native_dir,
        encoding="utf-8",
    )

    settings = env_to_settings(env_path, SettingsInfo, environ={})

    assert settings.CURL_CFFI_RUNTIME_DIR == native_dir
