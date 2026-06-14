"""
Request fingerprint helpers (no crawler dependency).

Used by dupefilter implementations and usable standalone with any object
that exposes url, headers, find_header_key, and Http/WebSocket payload fields.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, List, Protocol, runtime_checkable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..utils.algorithm import do_sha1


@runtime_checkable
class FingerprintRequest(Protocol):
    url: str
    headers: Any

    def find_header_key(self, key: str) -> Any: ...


def canonical_request_url(url: str) -> str:
    """Sort query pairs so ?b=1&a=2 and ?a=2&b=1 fingerprint identically."""
    parsed = urlparse(url)
    if not parsed.query:
        return url
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    return urlunparse(parsed._replace(query=urlencode(sorted(pairs))))


def build_fingerprint_bytes(
    request: FingerprintRequest,
    *,
    include_headers: Iterable[str] | None = None,
    method: str | None = None,
    body_parts: List[bytes] | None = None,
) -> bytes:
    include_headers = list(include_headers or [])
    header_subset = {}
    for header_key in include_headers:
        has_header_key = request.find_header_key(key=header_key)
        if has_header_key:
            header_subset[has_header_key.lower()] = request.headers[has_header_key]
    parts = [
        f"{canonical_request_url(request.url)}|"
        f"{json.dumps(header_subset, separators=(',', ':'), sort_keys=True)}".encode("latin-1")
    ]
    if method is not None:
        parts.append(f"{method}|".encode("latin-1"))
    if body_parts:
        parts.extend(body_parts)
    return b"".join(parts)


def fingerprint_sha1(fingerprint_bytes: bytes) -> str:
    return do_sha1(fingerprint_bytes)


__all__ = [
    "FingerprintRequest",
    "canonical_request_url",
    "build_fingerprint_bytes",
    "fingerprint_sha1",
]
