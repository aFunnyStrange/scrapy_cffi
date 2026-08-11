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
    "ProtobufCodecProtocol",
    "PythonProtobufCodec",
    "RustProtobufCodec",
    "WebSocketFlag",
    "select_protobuf_codec",
]
