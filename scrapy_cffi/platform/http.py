"""Define HTTP and WebSocket capabilities consumed by the crawler core."""

from enum import IntFlag
from typing import Any, AsyncIterator, Callable, Dict, Iterable, Optional, Protocol


class HttpTransportError(ConnectionError):
    """Report a request-library failure through a framework-owned exception."""


class WebSocketFlag(IntFlag):
    """Define stable WebSocket frame flags independent of the HTTP vendor."""

    TEXT = 1
    BINARY = 2
    CONT = 4
    CLOSE = 8
    PING = 16
    OFFSET = 32


class CookieJarProtocol(Protocol):
    """Describe cookie operations required by persistent crawler sessions."""

    jar: Iterable[Any]

    def set(self, name: str, value: str, **kwargs: Any) -> None:
        """Set one cookie in the underlying jar."""
        ...

    def clear(self) -> None:
        """Remove all cookies from the jar."""
        ...

    def get_dict(self) -> Dict[str, str]:
        """Return a simple name/value cookie mapping."""
        ...


class HttpResponseProtocol(Protocol):
    """Describe the response fields used by downloader response wrappers."""

    @property
    def status_code(self) -> int:
        """Return the HTTP status code."""
        ...

    @property
    def content(self) -> bytes:
        """Return the buffered response body."""
        ...

    @property
    def text(self) -> str:
        """Return the decoded buffered response body."""
        ...

    @property
    def headers(self) -> Any:
        """Return response headers."""
        ...


class AsyncWebSocketProtocol(Protocol):
    """Provide version-independent asynchronous WebSocket operations."""

    async def send(self, payload: Any, flags: Any = None) -> None:
        """Send one WebSocket frame."""
        ...

    async def recv(self, timeout: Optional[float] = None) -> Any:
        """Receive one WebSocket frame using stable async semantics."""
        ...

    async def close(self) -> None:
        """Close the WebSocket idempotently."""
        ...


class AsyncHttpStreamProtocol(Protocol):
    """Describe a live streaming response owned by its consumer."""

    @property
    def status_code(self) -> int:
        """Return the stream HTTP status code."""
        ...

    @property
    def headers(self) -> Any:
        """Return stream response headers."""
        ...

    def aiter_bytes(self, chunk_size: Optional[int] = None) -> AsyncIterator[bytes]:
        """Iterate response body chunks without buffering the complete body."""
        ...

    def aiter_lines(self) -> AsyncIterator[str]:
        """Iterate decoded response lines."""
        ...

    async def close(self) -> None:
        """Release the streaming request and its connection."""
        ...


class AsyncHttpSessionProtocol(Protocol):
    """Provide the HTTP session capability required by crawler components."""

    cookies: CookieJarProtocol

    async def request(self, method: str, **kwargs: Any) -> HttpResponseProtocol:
        """Perform one HTTP request."""
        ...

    async def connect_websocket(self, **kwargs: Any) -> AsyncWebSocketProtocol:
        """Open one WebSocket and normalize its lifecycle."""
        ...

    async def open_stream(self, method: str, **kwargs: Any) -> AsyncHttpStreamProtocol:
        """Open a live response stream whose consumer owns closure."""
        ...

    async def close(self) -> None:
        """Close the session and its pooled resources."""
        ...


HttpSessionFactory = Callable[[], AsyncHttpSessionProtocol]

__all__ = [
    "AsyncHttpSessionProtocol",
    "AsyncHttpStreamProtocol",
    "AsyncWebSocketProtocol",
    "CookieJarProtocol",
    "HttpResponseProtocol",
    "HttpSessionFactory",
    "HttpTransportError",
    "WebSocketFlag",
]
