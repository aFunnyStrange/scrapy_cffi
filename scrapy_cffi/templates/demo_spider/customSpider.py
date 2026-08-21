"""In-memory Demo spider covering process, HTTP, and WebSocket flows."""

from demo_support.endpoints import DEMO_PROCESS_URL, DEMO_QUIC_URL, DEMO_WS_URL
from demo_support.process_tasks import double_in_worker
from items.item import CustomItem
from scrapy_cffi.exceptions import Failure
from scrapy_cffi.internet import (
    CloseSignal,
    HttpResponse,
    WebSocketMsg,
    WebSocketRequest,
    WebSocketResponse,
    HttpRequest,
)
from scrapy_cffi.platform import HttpVersion, WebSocketFlag
from scrapy_cffi.spiders import Spider
from scrapy_cffi.utils import create_uniqueId


class CustomSpider(Spider):
    """Exercise a connection-and-send WebSocket followed by explicit stop."""

    name = "customSpider"
    robot_scheme = "http"
    allowed_domains = ["api.ipify.org", "127.0.0.1", "localhost"]
    start_urls = [DEMO_PROCESS_URL]
    async def parse(self, response: HttpResponse):
        """Await short process work, then open the event-driven socket."""
        self.session_id = create_uniqueId()
        print(response.text)
        process_result = await self.run_in_process(
            double_in_worker,
            value=response.json()["value"],
        )
        print({"short_process_result": process_result})
        yield HttpRequest(
            session_id=self.session_id,
            url=DEMO_QUIC_URL,
            http_version=HttpVersion.HTTP_3_ONLY,
            verify=False,
            callback=self.open_websocket,
            errback=self.errRet,
        )

    async def open_websocket(self, response: HttpResponse):
        """Record the finite HTTP/3 response before opening WebSocket."""
        print({"quic_demo": response.json()})
        yield self._new_websocket_request()

    def _new_websocket_request(self) -> WebSocketRequest:
        """Build the socket request shared by HTTP/3 success and fallback."""
        return WebSocketRequest(
            session_id=self.session_id,
            url=DEMO_WS_URL,
            headers=self.settings.DEFAULT_HEADERS,
            cookies=self.settings.DEFAULT_COOKIES,
            proxies=self.settings.PROXIES,
            timeout=self.settings.TIMEOUT,
            dont_filter=self.settings.DONT_FILTER,
            callback=self.sec_test,
            errback=self.errRet,
            send_message=WebSocketMsg(
                data=b"connect send test",
                flags=WebSocketFlag.BINARY,
            ),
        )

    async def sec_test(self, response: WebSocketResponse):
        """Advance from the actual echoed frame, never callback timing."""
        data = response.msg[0].decode()
        print({"session_id": response.session_id, "data": data})
        next_message = None
        if data.endswith("connect send test"):
            next_message = "hello: 0"
        elif data.endswith("hello: 0"):
            next_message = "hello: 1"
        elif data.endswith("hello: 1"):
            next_message = "hello: 2"

        if next_message is not None:
            yield WebSocketRequest(
                session_id=self.session_id,
                websocket_id=response.websocket_id,
                send_message=WebSocketMsg(
                    data=next_message.encode("utf-8"),
                    flags=WebSocketFlag.BINARY,
                ),
            )
        elif data.endswith("hello: 2"):
            response.stop_listening()
            yield CustomItem(
                session_id=response.session_id,
                data=data,
            )
            yield CustomItem(session_id=response.session_id, data="spider end")
            yield CloseSignal(session_id=self.session_id, session_end=True)

    async def errRet(self, failure: Failure):
        """Expose failures and keep the Demo usable without experimental HTTP/3."""
        print(f"error output: {failure}")
        request = getattr(failure, "request", None)
        if request is not None and request.url == DEMO_QUIC_URL:
            print({"quic_demo": "HTTP/3 experimental request unavailable"})
            yield self._new_websocket_request()
            return
        yield None
