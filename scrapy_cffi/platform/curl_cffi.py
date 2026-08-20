"""Adapt supported curl_cffi releases to stable crawler transport semantics."""

import asyncio
import inspect
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Type, Union

from .http import (
    AsyncHttpStreamProtocol,
    AsyncWebSocketProtocol,
    CookieJarProtocol,
    HttpResponseProtocol,
    HttpTimeoutError,
    HttpTransportError,
)


def _transport_error(error: BaseException, operation: str) -> HttpTransportError:
    """Translate one curl failure while preserving timeout semantics."""
    code = getattr(error, "code", None)
    message = str(error).lower()
    error_type = (
        HttpTimeoutError
        if code == 28 or "timeout" in message or "timed out" in message
        else HttpTransportError
    )
    return error_type("curl_cffi %s failed" % operation)

@dataclass(frozen=True)
class _CurlVendor:
    """Store curl_cffi modules selected after optional native activation."""

    requests: Any
    constants: Any
    error: Type[BaseException]


_vendor: Optional[_CurlVendor] = None


def _load_vendor() -> _CurlVendor:
    """Import curl_cffi once after the native implementation is selected."""
    global _vendor

    if _vendor is None:
        vendor_root = import_module("curl_cffi")
        _vendor = _CurlVendor(
            requests=import_module("curl_cffi.requests"),
            constants=import_module("curl_cffi.const"),
            error=getattr(vendor_root, "CurlError"),
        )
    return _vendor


async def _call_websocket_method(method: Any, *args: Any, **kwargs: Any) -> Any:
    """Invoke an old synchronous or new asynchronous WebSocket method safely."""
    if inspect.iscoroutinefunction(method):
        return await method(*args, **kwargs)
    result = await asyncio.to_thread(method, *args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


class CurlCffiWebSocket:
    """Normalize curl_cffi WebSocket send, receive, and close operations."""

    def __init__(self, websocket: Any) -> None:
        """Wrap one WebSocket returned by any qualified curl_cffi release."""
        vendor = _load_vendor()
        self.raw_websocket = websocket
        self._constants = vendor.constants
        self._curl_error = vendor.error
        self._closed = False
        self._close_lock = asyncio.Lock()

    async def send(self, payload: Any, flags: Any = None) -> None:
        """Send a frame while preserving legacy optional flag behavior."""
        if flags is None:
            kwargs = {}
        else:
            vendor_flag = getattr(self._constants, "CurlWsFlag")(int(flags))
            kwargs = {"flags": vendor_flag}
        try:
            await _call_websocket_method(
                self.raw_websocket.send,
                payload,
                **kwargs,
            )
        except asyncio.CancelledError:
            raise
        except self._curl_error as exc:
            raise _transport_error(exc, "WebSocket send") from exc

    async def recv(self, timeout: Optional[float] = None) -> Any:
        """Receive a frame without exposing sync/async implementation changes."""
        kwargs = {} if timeout is None else {"timeout": timeout}
        try:
            return await _call_websocket_method(
                self.raw_websocket.recv,
                **kwargs,
            )
        except asyncio.CancelledError:
            raise
        except self._curl_error as exc:
            raise _transport_error(exc, "WebSocket receive") from exc

    async def close(self) -> None:
        """Close the wrapped WebSocket at most once."""
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            try:
                await _call_websocket_method(self.raw_websocket.close)
            except asyncio.CancelledError:
                raise
            except self._curl_error as exc:
                raise _transport_error(exc, "WebSocket close") from exc


class CurlCffiHttpStream:
    """Own one entered curl_cffi stream context until explicit closure."""

    def __init__(self, response: Any, context: Any) -> None:
        """Store the raw response and its async context manager."""
        self.raw_response = response
        self._context = context
        self._curl_error = _load_vendor().error
        self._closed = False
        self._close_lock = asyncio.Lock()

    @property
    def status_code(self) -> int:
        """Return the HTTP status code without buffering the body."""
        return self.raw_response.status_code

    @property
    def headers(self) -> Any:
        """Return response headers."""
        return self.raw_response.headers

    @property
    def content(self) -> bytes:
        """Expose already buffered content without forcing stream consumption."""
        return self.raw_response.content

    @property
    def text(self) -> str:
        """Expose already buffered text without forcing stream consumption."""
        return self.raw_response.text

    async def aiter_bytes(self, chunk_size: Optional[int] = None) -> AsyncIterator[bytes]:
        """Yield raw response chunks from curl_cffi."""
        try:
            async for chunk in self.raw_response.aiter_content(chunk_size=chunk_size):
                yield chunk
        except asyncio.CancelledError:
            raise
        except self._curl_error as exc:
            raise _transport_error(exc, "response stream") from exc

    async def aiter_lines(self) -> AsyncIterator[str]:
        """Yield decoded response lines from curl_cffi."""
        try:
            async for line in self.raw_response.aiter_lines(decode_unicode=False):
                if isinstance(line, bytes):
                    yield line.decode("utf-8", errors="replace")
                else:
                    yield line
        except asyncio.CancelledError:
            raise
        except self._curl_error as exc:
            raise _transport_error(exc, "response line stream") from exc

    async def close(self) -> None:
        """Exit the curl_cffi stream context at most once."""
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            try:
                await self._context.__aexit__(None, None, None)
            except asyncio.CancelledError:
                raise
            except self._curl_error as exc:
                raise _transport_error(exc, "response stream close") from exc


class CurlCffiHttpSession:
    """Wrap curl_cffi AsyncSession behind the framework transport contract."""

    def __init__(
        self,
        session: Optional[Any] = None,
        native_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        """Create an adapter, preserving the legacy direct activation option."""
        if native_dir is not None:
            from .curl_native import activate_curl_native_runtime
            from ..profiles import load_profile_manifest

            runtime = activate_curl_native_runtime(native_dir)
            load_profile_manifest(runtime.runtime_dir)
        vendor = _load_vendor()
        session_class = getattr(vendor.requests, "AsyncSession")
        self._curl_error = vendor.error
        self.raw_session = session or session_class()

    @property
    def cookies(self) -> CookieJarProtocol:
        """Expose the session cookie jar required by persistence support."""
        return self.raw_session.cookies

    async def request(self, method: str, **kwargs: Any) -> HttpResponseProtocol:
        """Perform an HTTP request and normalize vendor exceptions."""
        try:
            return await self.raw_session.request(method=method, **kwargs)
        except asyncio.CancelledError:
            raise
        except self._curl_error as exc:
            raise _transport_error(exc, "HTTP request") from exc

    async def connect_websocket(self, **kwargs: Any) -> AsyncWebSocketProtocol:
        """Open old and new curl_cffi WebSockets through one awaitable API."""
        try:
            candidate = self.raw_session.ws_connect(**kwargs)
            websocket = await candidate if inspect.isawaitable(candidate) else candidate
            return CurlCffiWebSocket(websocket)
        except asyncio.CancelledError:
            raise
        except self._curl_error as exc:
            raise _transport_error(exc, "WebSocket connection") from exc

    async def open_stream(self, method: str, **kwargs: Any) -> AsyncHttpStreamProtocol:
        """Enter the curl_cffi stream context and transfer ownership to a wrapper."""
        try:
            context = self.raw_session.stream(method=method, **kwargs)
            response = await context.__aenter__()
            return CurlCffiHttpStream(response=response, context=context)
        except asyncio.CancelledError:
            raise
        except self._curl_error as exc:
            raise _transport_error(exc, "HTTP stream connection") from exc

    async def close(self) -> None:
        """Close the underlying curl_cffi session."""
        try:
            result = self.raw_session.close()
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise HttpTransportError("curl_cffi session close failed") from exc


__all__ = ["CurlCffiHttpSession", "CurlCffiHttpStream", "CurlCffiWebSocket"]
