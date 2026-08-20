"""Expose stable platform contracts and lazily loaded implementations."""

from typing import TYPE_CHECKING, Any

from .http import (
    AsyncHttpSessionProtocol,
    AsyncHttpStreamProtocol,
    AsyncWebSocketProtocol,
    CookieJarProtocol,
    HttpResponseProtocol,
    HttpSessionFactory,
    HttpTimeoutError,
    HttpTransportError,
    WebSocketFlag,
)
from .protobuf import (
    ProtobufCodecProtocol,
    PythonProtobufCodec,
    RustProtobufCodec,
    select_protobuf_codec,
)

if TYPE_CHECKING:
    from .curl_cffi import CurlCffiHttpSession, CurlCffiHttpStream, CurlCffiWebSocket
from .bloom import (
    BloomFilterFactory,
    BloomFilterProtocol,
    PythonBloomFilter,
    RustBloomFilter,
    bloom_filter_factory,
)

__all__ = [
    "AsyncHttpSessionProtocol",
    "AsyncHttpStreamProtocol",
    "AsyncWebSocketProtocol",
    "BloomFilterFactory",
    "BloomFilterProtocol",
    "CookieJarProtocol",
    "CurlCffiHttpSession",
    "CurlCffiHttpStream",
    "CurlCffiWebSocket",
    "HttpResponseProtocol",
    "HttpSessionFactory",
    "HttpTimeoutError",
    "HttpTransportError",
    "ProtobufCodecProtocol",
    "PythonBloomFilter",
    "PythonProtobufCodec",
    "RustProtobufCodec",
    "RustBloomFilter",
    "WebSocketFlag",
    "select_protobuf_codec",
    "bloom_filter_factory",
]

_LAZY_CURL_EXPORTS = {
    "CurlCffiHttpSession",
    "CurlCffiHttpStream",
    "CurlCffiWebSocket",
}


def __getattr__(name: str) -> Any:
    """Load curl_cffi only when its concrete adapter is selected."""
    if name in _LAZY_CURL_EXPORTS:
        from . import curl_cffi as _curl_cffi

        return getattr(_curl_cffi, name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    """Return the complete typed public platform surface."""
    return list(__all__)
