"""Apply browser Client Hints as mandatory session-aware middleware."""

import inspect
from collections.abc import MutableMapping
from typing import Any, List, Optional, TYPE_CHECKING

from .base import DownloadInterceptor
from ..core.client_hints import (
    NATIVE_DEFAULT_CLIENT_HINTS,
    client_hint_origin,
    parse_client_hint_names,
)
from ..core.downloader.internet import HttpRequest, HttpResponse, StreamResponse
from ..profiles import DEFAULT_REGISTRY
from ..utils import init_logger

if TYPE_CHECKING:
    from ..core.sessions import SessionManager
    from ..crawler import Crawler
    from ..spiders import BaseSpider


def _header_values(headers: Any, name: str) -> Optional[List[str]]:
    """Return every case-insensitive header value or None when absent."""
    if headers is None:
        return None
    get_list = getattr(headers, "get_list", None)
    if callable(get_list):
        values = get_list(name)
        return [str(value or "") for value in values] if values else None
    items = getattr(headers, "items", None)
    if not callable(items):
        return None
    values = [
        str(value or "")
        for key, value in items()
        if str(key).lower() == name.lower()
    ]
    return values or None


def _has_request_header(headers: Any, name: str) -> bool:
    """Check mapping and tuple-list request headers case-insensitively."""
    if headers is None:
        return False
    if isinstance(headers, MutableMapping):
        return any(str(key).lower() == name.lower() for key in headers)
    if isinstance(headers, list):
        return any(
            isinstance(item, tuple)
            and len(item) == 2
            and str(item[0]).lower() == name.lower()
            for item in headers
        )
    return False


def _append_request_header(headers: Any, name: str, value: str) -> bool:
    """Append one missing header while preserving the caller's container."""
    if isinstance(headers, MutableMapping):
        headers[name] = value
        return True
    if isinstance(headers, list):
        headers.append((name, value))
        return True
    return False


class ClientHintsDownloadInterceptor(DownloadInterceptor):
    """Observe Accept-CH and enrich later requests in the same session."""

    def __init__(
        self,
        sessions: "SessionManager",
        **kwargs: Any,
    ) -> None:
        """Bind the interceptor to the crawler-owned SessionManager."""
        super().__init__(**kwargs)
        self.sessions = sessions
        self.logger = init_logger(
            log_info=self.settings.LOG_INFO,
            logger_name=__name__,
        )

    @classmethod
    def from_crawler(cls, crawler: "Crawler") -> "ClientHintsDownloadInterceptor":
        """Construct the mandatory interceptor from crawler-owned resources."""
        return cls(
            sessions=crawler.sessions,
            stop_event=crawler.stop_event,
            settings=crawler.settings,
            resources=crawler.resources,
            kafka_repository=crawler.resources.kafka,
        )

    async def request_intercept(
        self,
        request: HttpRequest,
        spider: "BaseSpider",
    ) -> None:
        """Inject known hints without creating a replacement request."""
        if not isinstance(request, HttpRequest) or not request.impersonate:
            return None
        origin = client_hint_origin(request.url)
        if origin is None:
            return None
        wrapper = self.sessions.get_or_create_session(request.session_id)
        if request.headers is None:
            request.headers = {}
        for name, value in wrapper.client_hints.headers_for_request(
            origin,
            str(request.impersonate),
            DEFAULT_REGISTRY,
        ):
            if _has_request_header(request.headers, name):
                continue
            if not _append_request_header(request.headers, name, value):
                if wrapper.client_hints.mark_warned(
                    origin,
                    str(request.impersonate),
                    "invalid-header-container",
                ):
                    self.logger.warning(
                        "Client Hints skipped for origin=%s profile=%s: "
                        "request.headers must be a mapping or tuple list",
                        origin,
                        request.impersonate,
                    )
                break
        return None

    async def response_intercept(
        self,
        request: HttpRequest,
        response: Any,
        spider: "BaseSpider",
    ) -> Any:
        """Update one session's origin policy before the spider callback."""
        if (
            not isinstance(request, HttpRequest)
            or not request.impersonate
            or not isinstance(response, (HttpResponse, StreamResponse))
        ):
            return response
        origin = client_hint_origin(request.url)
        if origin is None:
            return response
        response_headers = getattr(response.raw_response, "headers", None)
        wrapper = self.sessions.get_or_create_session(request.session_id)

        clear_values = _header_values(response_headers, "Clear-Site-Data") or []
        if any('"clienthints"' in value.lower() for value in clear_values):
            wrapper.client_hints.clear_origin(origin)

        accept_values = _header_values(response_headers, "Accept-CH")
        if accept_values is None:
            return response
        requested = parse_client_hint_names(",".join(accept_values))
        wrapper.client_hints.replace_requested(origin, requested)

        profile = str(request.impersonate)
        for normalized, requested_name in requested.items():
            if normalized in NATIVE_DEFAULT_CLIENT_HINTS:
                continue
            if (
                wrapper.client_hints.get_value(
                    origin,
                    profile,
                    normalized,
                    DEFAULT_REGISTRY,
                )
                is not None
            ):
                continue
            value = await self._resolve_spider_value(
                spider,
                requested_name,
                origin,
                response,
            )
            if value is not None:
                wrapper.client_hints.set_runtime_value(
                    origin,
                    profile,
                    normalized,
                    value,
                )
            elif wrapper.client_hints.mark_warned(
                origin,
                profile,
                normalized,
            ):
                self.logger.warning(
                    "Client Hint %s requested for origin=%s profile=%s has "
                    "no configured value; add profile manifest metadata or "
                    "override Spider.resolve_client_hint",
                    requested_name,
                    origin,
                    profile,
                )
        return response

    @staticmethod
    async def _resolve_spider_value(
        spider: "BaseSpider",
        name: str,
        origin: str,
        response: Any,
    ) -> Optional[str]:
        """Call the optional Spider resolver and validate its result."""
        resolver = getattr(spider, "resolve_client_hint", None)
        if not callable(resolver):
            return None
        value = resolver(name=name, origin=origin, response=response)
        if inspect.isawaitable(value):
            value = await value
        if value is not None and not isinstance(value, str):
            raise TypeError("resolve_client_hint must return str or None")
        return value


__all__ = ["ClientHintsDownloadInterceptor"]
