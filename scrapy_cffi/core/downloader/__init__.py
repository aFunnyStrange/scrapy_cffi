from .internet import (
    Request,
    HttpRequest,
    MediaRequest,
    WebSocketRequest,
    Response,
    HttpResponse,
    SSEEvent,
    StreamResponse,
    WebSocketResponse,
)
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .fetch import Downloader

__all__ = [
    "Downloader",
    "Request",
    "HttpRequest",
    "MediaRequest",
    "WebSocketRequest",
    "Response",
    "HttpResponse",
    "SSEEvent",
    "StreamResponse",
    "WebSocketResponse",
]


def __getattr__(name: str) -> Any:
    """Resolve the downloader implementation without eager core imports."""
    if name == "Downloader":
        from .fetch import Downloader

        return Downloader
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
