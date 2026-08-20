"""Verify the stable HTTP platform boundary, streaming, and SSE behavior."""

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from scrapy_cffi.core.downloader.internet import HttpRequest, SSEEvent, StreamResponse
from scrapy_cffi.core.sessions import SessionManager, SessionRequestLimiter, SessionWrapper
from scrapy_cffi.platform.curl_cffi import CurlCffiHttpSession
from scrapy_cffi.platform import HttpTimeoutError, HttpTransportError
from scrapy_cffi.settings import SettingsInfo


def test_utils_typed_lazy_exports_cover_runtime_symbols():
    """Keep IDE-only imports synchronized with the lazy utility registry."""
    import ast
    from pathlib import Path

    from scrapy_cffi.utils._exports import _EXPORTS

    source = Path("scrapy_cffi/utils/__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    typed_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            for child in ast.walk(node):
                if isinstance(child, ast.ImportFrom):
                    typed_names.update(alias.asname or alias.name for alias in child.names)
    assert set(_EXPORTS).issubset(typed_names)


def test_vendor_websocket_flags_coerce_to_framework_enum():
    """Existing CurlWsFlag callers must remain source compatible in 0.4."""
    from curl_cffi.const import CurlWsFlag
    from scrapy_cffi.models.api import WebSocketMsg
    from scrapy_cffi.platform import WebSocketFlag

    message = WebSocketMsg(data=b"ping", flags=CurlWsFlag.PING)
    assert message.flags is WebSocketFlag.PING


class _CookieJar:
    """Provide the cookie behavior required by SessionWrapper tests."""

    def __init__(self):
        self.values = {}
        self.jar = []

    def set(self, name, value, **kwargs):
        self.values[name] = value

    def clear(self):
        self.values.clear()

    def get_dict(self):
        return dict(self.values)


class _FakeHttpSession:
    """Act as a protocol-compatible HTTP implementation without inheritance."""

    def __init__(self):
        self.cookies = _CookieJar()
        self.closed = False

    async def request(self, method, **kwargs):
        return SimpleNamespace(status_code=200, content=b"ok", text="ok", headers={})

    async def connect_websocket(self, **kwargs):
        raise AssertionError("not used")

    async def open_stream(self, method, **kwargs):
        raise AssertionError("not used")

    async def close(self):
        self.closed = True


class _FakeStream:
    """Yield deterministic SSE lines and record lifecycle closure."""

    status_code = 200
    headers = {"content-type": "text/event-stream"}
    content = b""
    text = ""

    def __init__(self):
        self.closed = False

    async def aiter_bytes(self, chunk_size=None):
        yield b"data: hello\n\n"

    async def aiter_lines(self):
        for line in [
            "id: 7",
            "event: token",
            "data: hello",
            "data: world",
            "retry: 1500",
            "",
            ": keepalive",
            "data: done",
            "",
        ]:
            yield line

    async def close(self):
        self.closed = True


class _AsyncWebSocket:
    """Model the asynchronous WebSocket API used by newer curl_cffi."""

    def __init__(self):
        self.sent = []
        self.closed = False

    async def send(self, payload, flags=None):
        self.sent.append((payload, flags))

    async def recv(self, timeout=None):
        return b"new", 2

    async def close(self):
        self.closed = True


class _SyncWebSocket:
    """Model the synchronous methods exposed by older compatible releases."""

    def __init__(self):
        self.sent = []
        self.closed = False

    def send(self, payload, flags=None):
        self.sent.append((payload, flags))

    def recv(self, timeout=None):
        return b"old", 2

    def close(self):
        self.closed = True


class _WebSocketSession:
    """Return one configured socket through an awaitable ws_connect call."""

    def __init__(self, websocket):
        self.websocket = websocket
        self.cookies = _CookieJar()

    async def ws_connect(self, **kwargs):
        return self.websocket

    async def close(self):
        return None


class _FailingRequestSession:
    """Raise one configured error from the vendor request boundary."""

    def __init__(self, error):
        self.error = error
        self.cookies = _CookieJar()

    async def request(self, **kwargs):
        raise self.error

    async def close(self):
        return None


class _Handler(BaseHTTPRequestHandler):
    """Serve normal and SSE responses for the real curl adapter test."""

    def do_GET(self):
        if self.path == "/events":
            body = b"event: token\ndata: one\n\ndata: two\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            return
        body = b"platform-ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def test_session_wrapper_accepts_duck_typed_http_factory():
    """The crawler session boundary must accept a structural implementation."""

    async def run():
        wrapper = SessionWrapper(
            stop_event=asyncio.Event(),
            settings=SettingsInfo(ROBOTSTXT_OBEY=False),
            cookies={"token": "value"},
            http_session_factory=_FakeHttpSession,
        )
        response = await wrapper.do_request(HttpRequest(url="https://example.test"))
        assert response.text == "ok"
        assert wrapper.session.cookies.get_dict() == {"token": "value"}
        await wrapper.session_close()
        assert wrapper.session.closed is True

    asyncio.run(run())


def test_request_retry_override_retries_transport_timeout() -> None:
    """A request-level retry policy overrides crawler defaults."""

    class RetrySession(_FakeHttpSession):
        calls = 0

        async def request(self, method, **kwargs):
            del method, kwargs
            type(self).calls += 1
            if type(self).calls < 3:
                raise HttpTimeoutError("slow upstream")
            return SimpleNamespace(
                status_code=200,
                content=b"ok",
                text="ok",
                headers={},
            )

    async def run() -> None:
        RetrySession.calls = 0
        wrapper = SessionWrapper(
            stop_event=asyncio.Event(),
            settings=SettingsInfo(MAX_REQ_TIMES=1, DELAY_REQ_TIME=10),
            http_session_factory=RetrySession,
        )
        response = await wrapper.do_request(
            HttpRequest(
                url="https://example.test",
                max_retry_times=3,
                retry_delay=0,
            )
        )
        assert response.status_code == 200
        assert RetrySession.calls == 3
        await wrapper.session_close()

    asyncio.run(run())


def test_session_rate_limiter_spaces_one_session_and_none_is_unlimited() -> None:
    """Rate admission is per session, while None does not create a hidden cap."""

    async def run() -> None:
        limited = SessionRequestLimiter(20)
        loop = asyncio.get_running_loop()
        started = loop.time()
        await limited.wait()
        await limited.wait()
        assert loop.time() - started >= 0.04

        limited.configure(None)
        started = loop.time()
        await limited.wait()
        await limited.wait()
        assert loop.time() - started < 0.04

    asyncio.run(run())


def test_registered_session_explicit_none_overrides_global_rate() -> None:
    """Distinguish an omitted inherited rate from explicit unlimited None."""
    manager = SessionManager(
        stop_event=asyncio.Event(),
        settings=SettingsInfo(SESSION_REQUESTS_PER_SECOND=1),
        http_session_factory=_FakeHttpSession,
    )

    manager.register_sessions_batch(
        {"account": {}},
        requests_per_second=None,
    )

    wrapper = manager.get_or_create_session("account")
    assert wrapper.request_limiter.requests_per_second is None


def test_stream_response_parses_sse_and_releases_once():
    """SSE parsing must preserve event fields and close capacity idempotently."""

    async def run():
        stream = _FakeStream()
        released = []
        response = StreamResponse(stream=stream, release=lambda: released.append(True))
        events = [event async for event in response.aiter_sse()]
        assert events == [
            SSEEvent(data="hello\nworld", event="token", id="7", retry=1500),
            SSEEvent(data="done", id="7"),
        ]
        await response.aclose()
        await response.aclose()
        assert stream.closed is True
        assert released == [True]

    asyncio.run(run())


def test_stream_response_rejects_unbounded_sse_event():
    """One malicious SSE event must not grow memory without a bound."""

    async def run():
        response = StreamResponse(stream=_FakeStream())
        with pytest.raises(ValueError, match="max_event_size"):
            async for _ in response.aiter_sse(max_event_size=3):
                pass
        await response.aclose()

    asyncio.run(run())


def test_replaced_stream_response_is_closed_by_interceptor_chain():
    """A middleware redirect must release the stream it replaces."""

    async def run():
        from scrapy_cffi.interceptors.chains import InterruptibleChainManager

        stream = _FakeStream()
        released = []
        response = StreamResponse(stream=stream, release=lambda: released.append(True))

        class RedirectInterceptor:
            async def response_intercept(self, **kwargs):
                return HttpRequest(url="https://example.test/next")

        manager = InterruptibleChainManager.__new__(InterruptibleChainManager)
        manager.chain_tail = SimpleNamespace(instance=RedirectInterceptor(), prev=None)

        async def callback(result):
            return result

        result = await manager.response_intercept_chain(
            request=HttpRequest(url="https://example.test/start"),
            response=response,
            spider=None,
            callback=callback,
        )
        assert result.request.url.endswith("/next")
        assert stream.closed is True
        assert released == [True]

    asyncio.run(run())


@pytest.mark.parametrize("socket_type, expected", [(_AsyncWebSocket, b"new"), (_SyncWebSocket, b"old")])
def test_curl_adapter_normalizes_websocket_methods(socket_type, expected):
    """Both legacy sync methods and current async methods expose one async API."""

    async def run():
        raw_socket = socket_type()
        session = CurlCffiHttpSession(session=_WebSocketSession(raw_socket))
        websocket = await session.connect_websocket(url="wss://example.test")
        await websocket.send(b"hello", flags=2)
        assert await websocket.recv() == (expected, 2)
        await websocket.close()
        await websocket.close()
        assert raw_socket.sent == [(b"hello", 2)]
        assert raw_socket.closed is True

    asyncio.run(run())


def test_curl_adapter_does_not_retry_programming_errors():
    """Type errors must remain visible instead of becoming network retries."""
    from curl_cffi import CurlError

    async def run():
        bad_call = CurlCffiHttpSession(session=_FailingRequestSession(TypeError("bad option")))
        with pytest.raises(TypeError, match="bad option"):
            await bad_call.request("GET", url="https://example.test")

        failed_transport = CurlCffiHttpSession(
            session=_FailingRequestSession(CurlError("network"))
        )
        with pytest.raises(HttpTransportError) as error:
            await failed_transport.request("GET", url="https://example.test")
        assert isinstance(error.value.__cause__, CurlError)

        timed_out = CurlCffiHttpSession(
            session=_FailingRequestSession(CurlError("operation timed out", 28))
        )
        with pytest.raises(HttpTimeoutError) as timeout_error:
            await timed_out.request("GET", url="https://example.test")
        assert isinstance(timeout_error.value.__cause__, CurlError)

    asyncio.run(run())


def test_downloader_returns_typed_timeout_to_error_path() -> None:
    """Exhausted request timeouts become inspectable spider-path failures."""
    from scrapy_cffi.core.downloader.fetch import Downloader
    from scrapy_cffi.exceptions import RequestTimeoutError

    class TimeoutWrapper:
        async def do_request(self, request):
            del request
            raise HttpTimeoutError("upstream timed out")

    class Sessions:
        def get_or_create_session(self, session_id, cookies=None):
            del session_id, cookies
            return TimeoutWrapper()

        def release(self, session_id):
            del session_id

    class Signals:
        def send(self, **kwargs):
            del kwargs

    async def run() -> None:
        downloader = Downloader(
            stop_event=asyncio.Event(),
            settings=SettingsInfo(MAX_REQ_TIMES=1, DELAY_REQ_TIME=0),
            sessions=Sessions(),
            sessions_lock=asyncio.Lock(),
            signalManager=Signals(),
        )
        results = []

        async def callback(response, request):
            results.append((response, request))

        request = HttpRequest(
            url="https://timeout.test",
            timeout=1,
            max_retry_times=1,
            retry_delay=0,
        )
        await downloader.fetch_http(request, callback)
        failure, returned_request = results[0]
        assert isinstance(failure, RequestTimeoutError)
        assert failure.request is request
        assert failure.timeout == 1
        assert failure.attempts == 1
        assert returned_request is request

    asyncio.run(run())


def test_curl_adapter_supports_http_and_streaming():
    """The installed curl_cffi release must satisfy the stable platform API."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    async def run():
        session = CurlCffiHttpSession()
        base_url = "http://127.0.0.1:{0}".format(server.server_port)
        try:
            response = await session.request("GET", url=base_url + "/")
            assert response.status_code == 200
            assert response.content == b"platform-ok"

            stream = await session.open_stream("GET", url=base_url + "/events")
            try:
                lines = [line async for line in stream.aiter_lines()]
                assert "data: one" in lines
                assert "data: two" in lines
            finally:
                await stream.close()
        finally:
            await session.close()

    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_total_crawler_flow_consumes_sse_stream():
    """Run a complete memory-spider flow from request through item pipeline."""
    from scrapy_cffi.crawler import Crawler
    from scrapy_cffi.pipelines import Pipeline
    from scrapy_cffi.spiders import Spider

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    event_url = "http://127.0.0.1:{0}/events".format(server.server_port)

    class CapturePipeline(Pipeline):
        items = []

        async def process_item(self, item, spider):
            self.items.append(item)
            return item

    class StreamingSpider(Spider):
        name = "streaming_total"
        allowed_domains = ["127.0.0.1"]

        async def start(self):
            yield HttpRequest(url=event_url, stream=True, callback=self.parse)

        async def parse(self, response):
            events = [event.data async for event in response.aiter_sse()]
            yield {"events": events}

    async def run():
        settings = SettingsInfo(
            SPIDERS_PATH=StreamingSpider,
            ROBOTSTXT_OBEY=False,
            ITEM_PIPELINES_PATH=[CapturePipeline],
            MAX_CONCURRENT_REQ=2,
            MAX_SCHEDULER_LOOP_NUM=1,
        )
        crawler = Crawler()
        robot_task = await crawler.do_initialization(settings=settings, start_type=1)
        try:
            await asyncio.wait_for(crawler.start_engines(robot_task), timeout=10)
        finally:
            await crawler.shutdown()

    try:
        asyncio.run(run())
        assert CapturePipeline.items == [{"events": ["one", "two"]}]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
