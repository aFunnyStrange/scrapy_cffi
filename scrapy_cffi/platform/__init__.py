"""Expose stable platform contracts and the default HTTP implementation."""

from .http import (
    AsyncHttpSessionProtocol,
    AsyncHttpStreamProtocol,
    AsyncWebSocketProtocol,
    CookieJarProtocol,
    HttpResponseProtocol,
    HttpSessionFactory,
    HttpTransportError,
    WebSocketFlag,
)
from .curl_cffi import CurlCffiHttpSession, CurlCffiHttpStream, CurlCffiWebSocket

__all__ = [
    "AsyncHttpSessionProtocol",
    "AsyncHttpStreamProtocol",
    "AsyncWebSocketProtocol",
    "CookieJarProtocol",
    "CurlCffiHttpSession",
    "CurlCffiHttpStream",
    "CurlCffiWebSocket",
    "HttpResponseProtocol",
    "HttpSessionFactory",
    "HttpTransportError",
    "WebSocketFlag",
]
