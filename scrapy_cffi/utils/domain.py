"""Hostname-only allowed_domains matching (Scrapy-style; ports ignored)."""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse


def hostname_from_url(url: str) -> Optional[str]:
    host = urlparse(url).hostname
    return host.lower() if host else None


def hostname_from_allowed(entry: str) -> str:
    """
    Normalize an ``allowed_domains`` entry to hostname only.

    Accepts ``example.com``, ``127.0.0.1:8002``, ``http://host:8080``.
    """
    entry = entry.strip().lower()
    if not entry:
        return ""
    if "://" in entry:
        host = urlparse(entry).hostname
    else:
        host = urlparse(f"http://{entry}").hostname
    return (host or entry.split(":")[0]).lower()


def url_is_from_allowed_domains(url: str, allowed_domains: list[str]) -> bool:
    """Return True if *url*'s hostname matches any allowed domain (suffix ok)."""
    if not allowed_domains:
        return True

    host = hostname_from_url(url)
    if not host:
        return False

    for entry in allowed_domains:
        allowed = hostname_from_allowed(entry)
        if not allowed:
            continue
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def robots_txt_url(scheme: str, allowed_entry: str) -> str:
    """Build robots.txt URL; preserve explicit port in *allowed_entry* when present."""
    entry = allowed_entry.strip()
    if not entry:
        return f"{scheme}://localhost/robots.txt"
    if "://" in entry:
        base = entry.rstrip("/")
        return f"{base}/robots.txt"
    return f"{scheme}://{entry}/robots.txt"


__all__ = [
    "hostname_from_url",
    "hostname_from_allowed",
    "url_is_from_allowed_domains",
    "robots_txt_url",
]
