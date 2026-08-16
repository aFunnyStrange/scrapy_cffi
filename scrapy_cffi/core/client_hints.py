"""Maintain origin-scoped Client Hint preferences inside one HTTP session."""

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Set, Tuple
from urllib.parse import urlsplit

from ..profiles import ProfileRegistry


NATIVE_DEFAULT_CLIENT_HINTS = {
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
}


def client_hint_origin(url: str) -> Optional[str]:
    """Return a normalized secure origin eligible for Client Hints."""
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    port = parsed.port
    if port is None or port == 443:
        return "https://%s" % host
    return "https://%s:%s" % (host, port)


def parse_client_hint_names(value: str) -> Dict[str, str]:
    """Parse a comma-separated Client Hint header into normalized names."""
    result = {}
    for item in value.split(","):
        name = item.strip()
        if name:
            result[name.lower()] = name
    return result


@dataclass
class _OriginClientHints:
    """Store one origin's requested names and runtime-resolved values."""

    requested: Dict[str, str] = field(default_factory=dict)
    runtime_values: Dict[str, Dict[str, str]] = field(default_factory=dict)


class ClientHintsState:
    """Own Client Hint state for the lifetime of one SessionWrapper."""

    def __init__(self) -> None:
        """Create an empty origin cache and bounded warning registry."""
        self._origins: Dict[str, _OriginClientHints] = {}
        self._warned: Set[str] = set()

    def replace_requested(self, origin: str, names: Mapping[str, str]) -> None:
        """Replace the complete Accept-CH preference set for one origin."""
        state = self._origins.setdefault(origin, _OriginClientHints())
        state.requested = dict(names)

    def clear_origin(self, origin: str) -> None:
        """Clear preferences and resolved values for one origin."""
        self._origins.pop(origin, None)
        prefix = "%s\x00" % origin
        self._warned = {key for key in self._warned if not key.startswith(prefix)}

    def requested_names(self, origin: str) -> Dict[str, str]:
        """Return a copy of the accepted hint names for one origin."""
        state = self._origins.get(origin)
        return dict(state.requested) if state is not None else {}

    def set_runtime_value(
        self,
        origin: str,
        profile: str,
        name: str,
        value: str,
    ) -> None:
        """Store a resolver-provided value for one origin and profile."""
        state = self._origins.setdefault(origin, _OriginClientHints())
        values = state.runtime_values.setdefault(profile, {})
        values[name.lower()] = value

    def get_value(
        self,
        origin: str,
        profile: str,
        name: str,
        registry: ProfileRegistry,
    ) -> Optional[str]:
        """Resolve runtime metadata before registered profile metadata."""
        state = self._origins.get(origin)
        normalized = name.lower()
        if state is not None:
            runtime_value = state.runtime_values.get(profile, {}).get(normalized)
            if runtime_value is not None:
                return runtime_value
        spec = registry.get(profile)
        return spec.get_client_hint(name) if spec is not None else None

    def headers_for_request(
        self,
        origin: str,
        profile: str,
        registry: ProfileRegistry,
    ) -> List[Tuple[str, str]]:
        """Return requested headers whose values are known for this profile."""
        result = []
        for normalized, requested_name in self.requested_names(origin).items():
            if normalized in NATIVE_DEFAULT_CLIENT_HINTS:
                continue
            value = self.get_value(origin, profile, normalized, registry)
            if value is not None:
                result.append((requested_name, value))
        return result

    def mark_warned(self, origin: str, profile: str, name: str) -> bool:
        """Return true only for the first warning for one scoped hint."""
        key = "%s\x00%s\x00%s" % (origin, profile, name.lower())
        if key in self._warned:
            return False
        self._warned.add(key)
        return True

    def export_state(self) -> Dict[str, object]:
        """Return JSON-safe state for scheduler session persistence."""
        return {
            "origins": {
                origin: {
                    "requested": dict(state.requested),
                    "runtime_values": {
                        profile: dict(values)
                        for profile, values in state.runtime_values.items()
                    },
                }
                for origin, state in self._origins.items()
            }
        }

    def import_state(self, payload: object) -> None:
        """Restore validated state while tolerating absent legacy snapshots."""
        if not isinstance(payload, dict):
            return
        origins = payload.get("origins")
        if not isinstance(origins, dict):
            return
        restored = {}
        for origin, raw_state in origins.items():
            if not isinstance(origin, str) or not isinstance(raw_state, dict):
                continue
            requested = raw_state.get("requested", {})
            runtime_values = raw_state.get("runtime_values", {})
            if not isinstance(requested, dict) or not isinstance(runtime_values, dict):
                continue
            clean_requested = {
                str(name).lower(): str(display)
                for name, display in requested.items()
            }
            clean_values = {}
            for profile, values in runtime_values.items():
                if isinstance(profile, str) and isinstance(values, dict):
                    clean_values[profile] = {
                        str(name).lower(): str(value)
                        for name, value in values.items()
                    }
            restored[origin] = _OriginClientHints(
                requested=clean_requested,
                runtime_values=clean_values,
            )
        self._origins = restored
        self._warned.clear()


__all__ = [
    "ClientHintsState",
    "NATIVE_DEFAULT_CLIENT_HINTS",
    "client_hint_origin",
    "parse_client_hint_names",
]
