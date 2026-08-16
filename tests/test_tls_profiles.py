"""Verify request-scoped TLS profile integration from API to transport."""

import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scrapy_cffi.core.sessions import SessionWrapper
from scrapy_cffi.internet import HttpRequest, MediaRequest, WebSocketRequest
from scrapy_cffi.interceptors.spiders import UpdateRequestSpiderInterceptor
from scrapy_cffi.profiles import (
    DEFAULT_REGISTRY,
    ActivationInfo,
    NativeActivationError,
    ProfileManifestError,
    ProfileRegistry,
    activate_native,
    load_profile_manifest,
    register_profile,
    resolve_impersonate,
)
from scrapy_cffi.profiles import runtime as profile_runtime
from scrapy_cffi.settings import SettingsInfo


def test_unit_impersonate_without_headers_preserves_vendor_profile_defaults() -> None:
    """Avoid overriding an explicit impersonation profile with framework UA."""
    interceptor = UpdateRequestSpiderInterceptor.__new__(
        UpdateRequestSpiderInterceptor
    )
    interceptor.default_headers = {"Accept": "application/json"}
    interceptor.default_ua = "scrapy_cffiBot"
    interceptor.timeout = 30
    interceptor.dont_filter = False
    interceptor.proxies = None
    interceptor.proxies_list = []

    profiled = interceptor.pre_check(
        HttpRequest(url="https://example.test", impersonate="chrome151")
    )
    ordinary = interceptor.pre_check(HttpRequest(url="https://example.test"))

    assert profiled.headers == {}
    assert ordinary.headers == {
        "Accept": "application/json",
        "user-agent": "scrapy_cffiBot",
    }


class _CookieJar:
    """Provide the cookie operations required by SessionWrapper tests."""

    def __init__(self) -> None:
        """Create an empty compatible cookie jar."""
        self.jar = []
        self.values = {}

    def set(self, name, value, **kwargs):
        """Store one cookie value."""
        self.values[name] = value

    def clear(self):
        """Clear all cookie values."""
        self.values.clear()

    def get_dict(self):
        """Return a copy of stored cookie values."""
        return dict(self.values)


class _CaptureSession:
    """Capture the exact arguments crossing the HTTP platform boundary."""

    instances = []

    def __init__(self) -> None:
        """Create one capture session and retain it for assertions."""
        self.cookies = _CookieJar()
        self.calls = []
        self.stream_calls = []
        self.websocket_calls = []
        self.closed = False
        type(self).instances.append(self)

    async def request(self, method, **kwargs):
        """Record one request and return a minimal response."""
        self.calls.append((method, kwargs))
        return SimpleNamespace(status_code=200, content=b"ok", text="ok", headers={})

    async def connect_websocket(self, **kwargs):
        """Record one WebSocket connection request."""
        self.websocket_calls.append(kwargs)
        return SimpleNamespace()

    async def open_stream(self, method, **kwargs):
        """Record one streaming request."""
        self.stream_calls.append((method, kwargs))
        return SimpleNamespace()

    async def close(self):
        """Mark the fake transport closed."""
        self.closed = True


def test_unit_profile_resolution_is_explicit() -> None:
    """Resolve user aliases without introducing a framework-owned default."""
    registry = ProfileRegistry()
    register_profile(
        "my-browser-stable",
        "my_native_profile_v1",
        registry=registry,
    )
    assert registry.resolve("my-browser-stable") == "my_native_profile_v1"
    assert registry.resolve("future_native_target") == "future_native_target"
    assert DEFAULT_REGISTRY.resolve("unregistered-profile") == "unregistered-profile"
    assert (
        resolve_impersonate(
            "my-browser-stable",
            registry=registry,
        )
        == "my_native_profile_v1"
    )
    assert resolve_impersonate(None) is None
    assert resolve_impersonate("vendor-profile") == "vendor-profile"


def test_unit_profile_registration_is_idempotent_and_conflict_safe() -> None:
    """Allow repeated activation while rejecting ambiguous alias ownership."""
    registry = ProfileRegistry()
    first = register_profile("stable", "native_v1", registry=registry)
    second = register_profile("stable", "native_v1", registry=registry)
    assert second is first
    with pytest.raises(ValueError, match="already registered"):
        register_profile("stable", "native_v2", registry=registry)


def test_unit_unregistered_runtime_uses_curl_cffi_fast_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skip alias lookup until a custom profile is actually registered."""
    registry = ProfileRegistry()
    resolved = []
    original_resolve = registry.resolve
    monkeypatch.setattr(
        registry,
        "resolve",
        lambda profile: resolved.append(profile) or original_resolve(profile),
    )

    assert registry.has_registered_profiles is False
    assert resolve_impersonate("vendor-profile", registry=registry) == "vendor-profile"
    assert resolved == []

    register_profile("custom-alias", "custom_native_v1", registry=registry)
    assert registry.has_registered_profiles is True
    assert resolve_impersonate("custom-alias", registry=registry) == "custom_native_v1"
    assert resolved == ["custom-alias"]


def test_unit_manifest_requires_supported_schema(tmp_path: Path) -> None:
    """Reject artifact manifests whose contract version is not supported."""
    (tmp_path / "scrapy_cffi_profiles.toml").write_text(
        'schema_version = 2\n[profiles]\nstable = "native_v1"\n',
        encoding="utf-8",
    )
    with pytest.raises(ProfileManifestError, match="schema_version"):
        load_profile_manifest(tmp_path, registry=ProfileRegistry())


def test_unit_manifest_loads_profile_client_hints(tmp_path: Path) -> None:
    """Load optional browser metadata while retaining legacy manifests."""
    (tmp_path / "scrapy_cffi_profiles.toml").write_text(
        """schema_version = 1
[profiles.stable]
impersonate = "native_v1"

[profiles.stable.client_hints]
Sec-CH-UA-Arch = '\"x86\"'
Sec-CH-UA-Bitness = '\"64\"'
""",
        encoding="utf-8",
    )
    registry = ProfileRegistry()

    profiles = load_profile_manifest(tmp_path, registry=registry)

    assert profiles[0].impersonate == "native_v1"
    assert profiles[0].get_client_hint("sec-ch-ua-arch") == '"x86"'
    assert registry.get("stable").get_client_hint("Sec-CH-UA-Bitness") == '"64"'


def test_unit_native_activation_rejects_missing_directory(tmp_path: Path) -> None:
    """Fail before vendor import when the configured artifact path is invalid."""
    with pytest.raises(NativeActivationError, match="does not exist"):
        activate_native(tmp_path / "missing")


def test_integration_runtime_loads_adjacent_profile_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compose native selection and manifest registration at runtime startup."""
    manifest = tmp_path / "scrapy_cffi_profiles.toml"
    manifest.write_text(
        'schema_version = 1\n[profiles]\nmy-browser-stable = "my_native_profile_v1"\n',
        encoding="utf-8",
    )
    wrapper_path = tmp_path / "_wrapper.test"
    wrapper_path.touch()
    activation = ActivationInfo(
        native_dir=tmp_path,
        wrapper_path=wrapper_path,
        platform=sys.platform,
    )
    monkeypatch.setattr(profile_runtime, "activate_native", lambda native_dir: activation)
    registry = ProfileRegistry()

    result = profile_runtime.activate_profile_runtime(tmp_path, registry=registry)

    assert result.native == activation
    assert [profile.name for profile in result.profiles] == ["my-browser-stable"]
    assert registry.resolve("my-browser-stable") == "my_native_profile_v1"


def test_integration_session_resolves_only_selected_request_profile() -> None:
    """Resolve a semantic alias at the framework-to-transport boundary."""
    _CaptureSession.instances.clear()
    register_profile("test-browser-stable", "test_native_profile_v1")

    async def run() -> None:
        """Send custom, official, and plain requests through one pooled session."""
        wrapper = SessionWrapper(
            stop_event=asyncio.Event(),
            settings=SettingsInfo(ROBOTSTXT_OBEY=False, MAX_REQ_TIMES=1),
            http_session_factory=_CaptureSession,
        )
        await wrapper.do_request(
            HttpRequest(
                url="https://custom.test",
                impersonate="test-browser-stable",
            )
        )
        await wrapper.do_request(
            HttpRequest(url="https://official.test", impersonate="vendor-profile")
        )
        await wrapper.do_request(
            HttpRequest(
                url="https://custom-through-impersonate.test",
                impersonate="test-browser-stable",
            )
        )
        await wrapper.do_request(HttpRequest(url="https://plain.test"))
        await wrapper.do_request(
            MediaRequest(
                url="https://media.test",
                headers={},
                media_size=1,
                impersonate="test-browser-stable",
            )
        )
        await wrapper.open_stream(
            HttpRequest(
                url="https://stream.test",
                stream=True,
                impersonate="test-browser-stable",
            )
        )
        await wrapper.ws_connect_once(
            WebSocketRequest(
                url="wss://websocket.test",
                impersonate="test-browser-stable",
            )
        )
        await wrapper.session_close()

    asyncio.run(run())
    session = _CaptureSession.instances[-1]
    assert [call[1]["impersonate"] for call in session.calls] == [
        "test_native_profile_v1",
        "vendor-profile",
        "test_native_profile_v1",
        None,
        "test_native_profile_v1",
    ]
    assert session.stream_calls[-1][1]["impersonate"] == "test_native_profile_v1"
    assert session.websocket_calls[-1]["impersonate"] == "test_native_profile_v1"
    assert session.closed is True


def test_total_profile_survives_request_persistence_and_execution() -> None:
    """Preserve explicit profile selection through the complete request flow."""
    _CaptureSession.instances.clear()
    register_profile("persisted-browser", "persisted_native_profile_v1")
    restored = HttpRequest.from_bytes(
        HttpRequest(
            url="https://persisted.test",
            impersonate="persisted-browser",
        ).to_bytes()
    )

    async def run() -> None:
        """Execute the restored public request through the real session wrapper."""
        wrapper = SessionWrapper(
            stop_event=asyncio.Event(),
            settings=SettingsInfo(ROBOTSTXT_OBEY=False, MAX_REQ_TIMES=1),
            http_session_factory=_CaptureSession,
        )
        response = await wrapper.do_request(restored)
        assert response.status_code == 200
        await wrapper.session_close()

    asyncio.run(run())
    method, kwargs = _CaptureSession.instances[-1].calls[-1]
    assert method == "GET"
    assert kwargs["impersonate"] == "persisted_native_profile_v1"


def test_public_request_import_does_not_preload_curl_cffi() -> None:
    """Keep activation optional through public imports and settings loading."""
    command = (
        "import sys; from pathlib import Path; import scrapy_cffi.internet; "
        "from scrapy_cffi.settings import SettingsInfo; "
        "SettingsInfo(CURL_CFFI_NATIVE_DIR=Path('optional-native')); "
        "assert not any(n == 'curl_cffi' or n.startswith('curl_cffi.') "
        "for n in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", command], check=True)
