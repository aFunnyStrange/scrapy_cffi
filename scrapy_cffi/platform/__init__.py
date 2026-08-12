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
from .protobuf import (
    ProtobufCodecProtocol,
    PythonProtobufCodec,
    RustProtobufCodec,
    select_protobuf_codec,
)
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
