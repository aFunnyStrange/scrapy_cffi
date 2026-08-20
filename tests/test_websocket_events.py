"""Verify event-driven WebSocket delivery and explicit listener shutdown."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from scrapy_cffi.core.downloader.fetch import Downloader
from scrapy_cffi.core.engine import Engine
from scrapy_cffi.core.sessions import WebSocketEntry
from scrapy_cffi.exceptions import SessionEndError
from scrapy_cffi.internet import WebSocketMsg, WebSocketRequest, WebSocketResponse
from scrapy_cffi.settings import SettingsInfo


class _Logger:
    """Capture no-op log calls required by lifecycle objects."""

    def debug(self, message) -> None:
        """Ignore debug output."""

    def warning(self, message) -> None:
        """Ignore warning output."""

    def error(self, message) -> None:
        """Ignore error output."""


class _SignalManager:
    """Record framework signals emitted by the downloader."""

    def __init__(self) -> None:
        """Create an empty signal record."""
        self.calls = []

    def send(self, signal, data) -> None:
        """Record one signal emission."""
        self.calls.append((signal, data))


class _WebSocket:
    """Return one message after verifying the initial send happened first."""

    def __init__(self) -> None:
        """Create a controllable fake socket."""
        self.sent = []
        self.closed = False
        self.recv_calls = 0

    async def send(self, payload, flags=None) -> None:
        """Record an outbound frame."""
        self.sent.append((payload, flags))

    async def recv(self):
        """Return one frame, then remain open until cancellation."""
        self.recv_calls += 1
        if self.recv_calls == 1:
            assert self.sent
            return b"first-message", 2
        await asyncio.Event().wait()

    async def close(self) -> None:
        """Mark the socket closed."""
        self.closed = True


class _Wrapper:
    """Bind a fake socket to one registered WebSocket entry."""

    def __init__(self, entry: WebSocketEntry, websocket: _WebSocket) -> None:
        """Store the entry and socket."""
        self.entry = entry
        self.websocket = websocket

    async def do_request(self, request, is_ws=False):
        """Return the connected fake socket."""
        assert is_ws is True
        return self.websocket

    def set_websocket(self, url, websocket) -> str:
        """Attach the socket and return a public connection identifier."""
        self.entry.set_websocket(websocket)
        return "websocket-id"


def test_unit_websocket_response_stop_is_idempotent() -> None:
    """Invoke the connection stop callback at most once."""
    calls = []
    response = WebSocketResponse(stop_listening=lambda: calls.append(True))

    response.stop_listening()
    response.stop_listening()

    assert calls == [True]


def test_unit_legacy_end_waits_for_active_callback_reference() -> None:
    """Route legacy CloseSignal semantics through the same stop event."""
    entry = WebSocketEntry(logger=_Logger(), url="wss://reference.test")

    entry.acquire()
    entry.mark_end()
    assert entry.stop_event.is_set() is False

    entry.release()
    assert entry.stop_event.is_set() is True


def test_unit_websocket_entry_construction_requires_no_event_loop() -> None:
    """Allow registration before an asyncio loop exists on Python 3.9."""

    def construct_and_stop() -> bool:
        """Construct in a worker thread, where no implicit loop is available."""
        entry = WebSocketEntry(logger=_Logger(), url="wss://no-loop.test")
        entry.mark_end()
        return entry.stop_event.is_set()

    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(construct_and_stop).result() is True


def test_integration_external_close_does_not_deadlock_listener_cleanup() -> None:
    """Cancel an owned listener whose finalizer also closes its entry."""

    async def run() -> None:
        """Reproduce external-close and listener-finalizer convergence."""
        entry = WebSocketEntry(logger=_Logger(), url="wss://close.test")

        async def listener() -> None:
            """Wait indefinitely and run the normal listener finalizer."""
            try:
                await asyncio.Event().wait()
            finally:
                await entry.close()

        task = asyncio.create_task(listener())
        entry.set_listener_task(task)
        await asyncio.sleep(0)
        await asyncio.wait_for(entry.close(), timeout=1)

        assert task.done()
        assert entry.stop_event.is_set()
        assert entry.closed_event.is_set()

    asyncio.run(run())


def test_integration_websocket_dispatches_events_without_end_sentinel() -> None:
    """Send immediately, dispatch directly, and stop through response control."""

    async def run() -> None:
        """Exercise downloader, entry, response, and socket lifecycle together."""
        stop_event = asyncio.Event()
        settings = SettingsInfo(
            ROBOTSTXT_OBEY=False,
            MAX_CONCURRENT_REQ=2,
        )
        signal_manager = _SignalManager()
        downloader = Downloader(
            stop_event=stop_event,
            settings=settings,
            sessions=None,
            sessions_lock=asyncio.Lock(),
            signalManager=signal_manager,
        )
        entry = WebSocketEntry(logger=_Logger(), url="wss://events.test")
        websocket = _WebSocket()
        wrapper = _Wrapper(entry=entry, websocket=websocket)
        request = WebSocketRequest(
            url=entry.url,
            send_message=WebSocketMsg(data=b"connect-send"),
        )
        responses = []

        async def on_response(response, request) -> None:
            """Capture the frame and explicitly stop the long listener."""
            responses.append(response)
            response.stop_listening()

        task = asyncio.create_task(
            downloader._websocket_listener(
                entry=entry,
                wrapper=wrapper,
                request=request,
                callback=on_response,
            )
        )
        entry.set_listener_task(task)
        await asyncio.wait_for(entry.wait_closed(), timeout=1)
        await task

        assert websocket.sent[0][0] == b"connect-send"
        assert responses[0].msg[0] == b"first-message"
        assert entry.stop_event.is_set()
        assert entry.closed_event.is_set()
        assert websocket.closed is True
        assert signal_manager.calls

    asyncio.run(run())


def test_websocket_close_frame_is_not_dispatched_as_application_data() -> None:
    """Treat protocol close payloads as lifecycle events, not UTF-8 messages."""

    class CloseWebSocket(_WebSocket):
        async def recv(self):
            return b"\x03\xf3", 8

    async def run() -> None:
        entry = WebSocketEntry(logger=_Logger(), url="wss://close-frame.test")
        websocket = CloseWebSocket()
        wrapper = _Wrapper(entry=entry, websocket=websocket)
        downloader = Downloader(
            stop_event=asyncio.Event(),
            settings=SettingsInfo(),
            sessions=None,
            sessions_lock=asyncio.Lock(),
            signalManager=_SignalManager(),
        )
        responses = []

        async def callback(response, request):
            responses.append((response, request))

        request = WebSocketRequest(url=entry.url)
        task = asyncio.create_task(
            downloader._websocket_listener(
                entry=entry,
                wrapper=wrapper,
                request=request,
                callback=callback,
            )
        )
        entry.set_listener_task(task)
        await asyncio.wait_for(entry.wait_closed(), timeout=1)
        await task

        assert responses == []
        assert entry.stop_event.is_set()
        assert websocket.closed is True

    asyncio.run(run())


def test_total_engine_waits_for_websocket_closed_event() -> None:
    """Run the Engine connection boundary through final session cleanup."""

    async def run() -> None:
        """Verify the complete Engine ownership path without a message queue."""
        entry = WebSocketEntry(logger=_Logger(), url="wss://engine.test")
        released = []
        closed = []

        class _Downloader:
            """Return an entry whose listener completes asynchronously."""

            async def fetch_websocket(self, wrapper, request, callback):
                """Start a bounded listener-completion task."""
                async def complete() -> None:
                    """Signal listener completion on the next loop turn."""
                    await asyncio.sleep(0)
                    entry.closed_event.set()

                asyncio.create_task(complete())
                return entry

        class _Sessions:
            """Record the released logical session."""

            def release(self, session_id) -> None:
                """Record one session release."""
                released.append(session_id)

        class _EngineWrapper:
            """Record final WebSocket closure."""

            async def close_websocket(self, identifier) -> None:
                """Record the connection identifier."""
                closed.append(identifier)

        engine = Engine.__new__(Engine)
        engine.downloader = _Downloader()
        engine.sessions = _Sessions()
        engine.logger = _Logger()
        engine.process_downloadInterceptor_chain = lambda **kwargs: None
        request = WebSocketRequest(
            session_id="session-1",
            url=entry.url,
            send_message=WebSocketMsg(data=b"connect-send"),
        )

        await engine.do_websocket_connect(_EngineWrapper(), request)

        assert released == ["session-1"]
        assert closed == [entry.url]

    asyncio.run(run())


def test_engine_does_not_reconnect_a_stale_websocket_send() -> None:
    """A queued follow-up cannot become a fresh listener after close."""

    async def run() -> None:
        """Exercise the close-between-enqueue-and-download race."""
        released = []
        responses = []
        reconnects = []

        class _Pool:
            """Represent a pool whose target listener has already closed."""

            def get_from_key(self, key):
                """Return no entry for the stale public identifier."""
                return None

        class _Wrapper:
            """Expose the closed WebSocket pool."""

            websocket_pool = _Pool()

        class _Sessions:
            """Record session release after the stale request is rejected."""

            def get_or_create_session(self, session_id, cookies=None):
                """Return the wrapper without recreating transport state."""
                return _Wrapper()

            def release(self, session_id) -> None:
                """Record balanced session ownership."""
                released.append(session_id)

        engine = Engine.__new__(Engine)
        engine.sessions = _Sessions()

        async def process_response(response, request) -> None:
            """Capture the normal downloader exception path."""
            responses.append((response, request))

        async def reconnect(wrapper, request) -> None:
            """Fail the test if a stale send is treated as a connection."""
            reconnects.append(request)

        engine.process_downloadInterceptor_chain = process_response
        engine.do_websocket_connect = reconnect
        request = WebSocketRequest(
            session_id="session-1",
            websocket_id="closed-websocket",
            url="wss://events.test",
            send_message=WebSocketMsg(data=b"late-send"),
        )

        await engine.process_websocket_request(request)

        assert reconnects == []
        assert released == ["session-1"]
        assert isinstance(responses[0][0], SessionEndError)
        assert responses[0][1] is request

    asyncio.run(run())
