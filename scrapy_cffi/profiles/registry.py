"""Register explicit request profiles and their browser metadata."""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple, Union

import toml


PROFILE_MANIFEST_NAME = "scrapy_cffi_profiles.toml"
PROFILE_MANIFEST_SCHEMA_VERSION = 1
ImpersonateResolver = Callable[[Optional[str]], Optional[str]]
ClientHintItems = Tuple[Tuple[str, str], ...]
_CLIENT_HINT_NAME_RE = re.compile(r"^[A-Za-z0-9-]+$")
_LEGACY_CLIENT_HINT_NAMES = {
    "device-memory",
    "downlink",
    "dpr",
    "ect",
    "rtt",
    "save-data",
    "viewport-width",
    "width",
}


class ProfileManifestError(ValueError):
    """Report an invalid profile manifest owned by a native artifact folder."""


@dataclass(frozen=True)
class ProfileSpec:
    """Describe one stable profile alias and optional Client Hint values."""

    name: str
    impersonate: str
    client_hints: ClientHintItems = ()

    def get_client_hint(self, name: str) -> Optional[str]:
        """Return a configured Client Hint value case-insensitively."""
        normalized = name.lower()
        for hint_name, value in self.client_hints:
            if hint_name.lower() == normalized:
                return value
        return None


class ProfileRegistry:
    """Own profile aliases without selecting a process-wide request default."""

    def __init__(self, profiles: Iterable[ProfileSpec] = ()) -> None:
        """Create a registry from optional initial profile definitions."""
        self._profiles: Dict[str, ProfileSpec] = {}
        self._has_registered_profiles = False
        self._impersonate_resolver: ImpersonateResolver = self._passthrough
        for profile in profiles:
            self.register(profile)

    @property
    def has_registered_profiles(self) -> bool:
        """Return whether custom alias lookup is active for this process."""
        return self._has_registered_profiles

    @property
    def impersonate_resolver(self) -> ImpersonateResolver:
        """Return the callback selected by registry initialization."""
        return self._impersonate_resolver

    @staticmethod
    def _passthrough(impersonate: Optional[str]) -> Optional[str]:
        """Return curl_cffi profile values without registry lookup."""
        return impersonate

    def _resolve_registered(self, impersonate: Optional[str]) -> Optional[str]:
        """Resolve a registered alias while preserving unknown values."""
        if impersonate is None:
            return None
        return self.resolve(impersonate)

    def register(self, profile: ProfileSpec, replace: bool = False) -> ProfileSpec:
        """Register one alias, optionally replacing an existing alias.

        Repeating the same definition is idempotent so multiple sessions can
        activate the same configured artifact directory safely.
        """
        if not profile.name:
            raise ValueError("Profile name cannot be empty")
        if not profile.impersonate:
            raise ValueError("Native impersonate target cannot be empty")
        current = self._profiles.get(profile.name)
        if current == profile:
            return current
        if current is not None and not replace:
            raise ValueError("Profile is already registered: %s" % profile.name)
        self._profiles[profile.name] = profile
        if not self._has_registered_profiles:
            self._has_registered_profiles = True
            self._impersonate_resolver = self._resolve_registered
        return profile

    def resolve(self, profile: str) -> str:
        """Resolve a known alias and pass unknown native names through."""
        registered = self._profiles.get(profile)
        return registered.impersonate if registered is not None else profile

    def get(self, profile: str) -> Optional[ProfileSpec]:
        """Return metadata for a registered alias without native fallback."""
        return self._profiles.get(profile)


DEFAULT_REGISTRY = ProfileRegistry()


def register_profile(
    name: str,
    impersonate: str,
    replace: bool = False,
    registry: ProfileRegistry = DEFAULT_REGISTRY,
    client_hints: Optional[Mapping[str, str]] = None,
) -> ProfileSpec:
    """Register a user-owned alias for one compiled native target."""
    return registry.register(
        ProfileSpec(
            name=name,
            impersonate=impersonate,
            client_hints=_validate_client_hints(
                client_hints or {},
                "profile %s" % name,
            ),
        ),
        replace=replace,
    )


def _validate_client_hints(
    value: object,
    source: str,
) -> ClientHintItems:
    """Validate browser metadata without permitting arbitrary headers."""
    if not isinstance(value, dict):
        raise ProfileManifestError(
            "Client Hints must be a table in %s" % source
        )
    result = []
    for name, hint_value in value.items():
        if not isinstance(name, str) or not _CLIENT_HINT_NAME_RE.fullmatch(name):
            raise ProfileManifestError(
                "Client Hint names must be HTTP tokens in %s" % source
            )
        normalized = name.lower()
        if (
            not normalized.startswith("sec-ch-")
            and normalized not in _LEGACY_CLIENT_HINT_NAMES
        ):
            raise ProfileManifestError(
                "Unsupported Client Hint name %r in %s" % (name, source)
            )
        if not isinstance(hint_value, str):
            raise ProfileManifestError(
                "Client Hint values must be strings in %s" % source
            )
        result.append((name, hint_value))
    return tuple(result)


def _validate_manifest_profiles(
    value: object,
    manifest_path: Path,
) -> List[ProfileSpec]:
    """Validate legacy strings and metadata-rich profile tables."""
    if not isinstance(value, dict):
        raise ProfileManifestError(
            "Manifest [profiles] must be a table: %s" % manifest_path
        )
    profiles = []
    for name, definition in value.items():
        if not isinstance(name, str) or not name.strip():
            raise ProfileManifestError(
                "Manifest profile names must be non-empty strings: %s"
                % manifest_path
            )
        if isinstance(definition, str):
            target = definition
            client_hints = ()
        elif isinstance(definition, dict):
            unknown = set(definition) - {"impersonate", "client_hints"}
            if unknown:
                raise ProfileManifestError(
                    "Unknown profile fields %r in %s"
                    % (sorted(unknown), manifest_path)
                )
            target = definition.get("impersonate")
            client_hints = _validate_client_hints(
                definition.get("client_hints", {}),
                "%s profile %s" % (manifest_path, name),
            )
        else:
            target = None
            client_hints = ()
        if not isinstance(target, str) or not target.strip():
            raise ProfileManifestError(
                "Manifest profile targets must be non-empty strings: %s"
                % manifest_path
            )
        profiles.append(
            ProfileSpec(
                name=name,
                impersonate=target,
                client_hints=client_hints,
            )
        )
    return profiles


def load_profile_manifest(
    native_dir: Union[str, Path],
    registry: ProfileRegistry = DEFAULT_REGISTRY,
) -> List[ProfileSpec]:
    """Load optional aliases declared beside a self-built native wrapper.

    Args:
        native_dir: Artifact directory containing the optional manifest.
        registry: Registry receiving the declared aliases.

    Returns:
        Profiles registered from the manifest, or an empty list when absent.

    Raises:
        ProfileManifestError: If the manifest cannot be read or is invalid.
        ValueError: If an alias conflicts with an existing registration.
    """
    manifest_path = Path(native_dir).expanduser().resolve() / PROFILE_MANIFEST_NAME
    if not manifest_path.is_file():
        return []
    try:
        manifest = toml.load(str(manifest_path))
    except (OSError, TypeError, toml.TomlDecodeError) as exc:
        raise ProfileManifestError(
            "Unable to read profile manifest: %s" % manifest_path
        ) from exc
    schema_version = manifest.get("schema_version")
    if schema_version != PROFILE_MANIFEST_SCHEMA_VERSION:
        raise ProfileManifestError(
            "Unsupported profile manifest schema_version %r in %s; expected %s"
            % (
                schema_version,
                manifest_path,
                PROFILE_MANIFEST_SCHEMA_VERSION,
            )
        )
    profiles = _validate_manifest_profiles(manifest.get("profiles"), manifest_path)
    return [
        registry.register(profile)
        for profile in profiles
    ]


def resolve_impersonate(
    impersonate: Optional[str],
    registry: ProfileRegistry = DEFAULT_REGISTRY,
) -> Optional[str]:
    """Resolve one explicit impersonate value without a global default.

    Registered aliases resolve to their user-owned native targets. Unknown
    values pass through unchanged so curl_cffi built-in profiles and direct
    native targets remain compatible.
    """
    return registry.impersonate_resolver(impersonate)


def get_impersonate_resolver(
    registry: ProfileRegistry = DEFAULT_REGISTRY,
) -> ImpersonateResolver:
    """Return the fixed callback selected after startup registration."""
    return registry.impersonate_resolver


__all__ = [
    "DEFAULT_REGISTRY",
    "ClientHintItems",
    "ImpersonateResolver",
    "PROFILE_MANIFEST_NAME",
    "PROFILE_MANIFEST_SCHEMA_VERSION",
    "ProfileManifestError",
    "ProfileRegistry",
    "ProfileSpec",
    "get_impersonate_resolver",
    "load_profile_manifest",
    "register_profile",
    "resolve_impersonate",
]
