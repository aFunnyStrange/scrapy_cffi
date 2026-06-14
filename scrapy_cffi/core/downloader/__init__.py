from .internet import (
    Request,
    HttpRequest,
    MediaRequest,
    WebSocketRequest,
    Response,
    HttpResponse,
    WebSocketResponse,
)

__all__ = [
    "Downloader",
    "Request",
    "HttpRequest",
    "MediaRequest",
    "WebSocketRequest",
    "Response",
    "HttpResponse",
    "WebSocketResponse",
]


def __getattr__(name: str):
    if name == "Downloader":
        from .fetch import Downloader

        return Downloader
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")