"""In-memory Demo spider covering HTTP and event-driven WebSocket flows."""

from demo_support.endpoints import DEMO_HTTP_URL, DEMO_WS_URL
from items.item import CustomItem
from scrapy_cffi.exceptions import Failure
from scrapy_cffi.internet import (
    CloseSignal,
    HttpResponse,
    WebSocketMsg,
    WebSocketRequest,
    WebSocketResponse,
)
from scrapy_cffi.platform import WebSocketFlag
from scrapy_cffi.spiders import Spider
from scrapy_cffi.utils import create_uniqueId


class CustomSpider(Spider):
    """Exercise a connection-and-send WebSocket followed by explicit stop."""

    name = "customSpider"
    robot_scheme = "http"
    allowed_domains = ["api.ipify.org", "127.0.0.1", "localhost"]
    start_urls = [DEMO_HTTP_URL]
    async def parse(self, response: HttpResponse):
        """Open one socket and send its first frame immediately."""
        self.session_id = create_uniqueId()
        print(response.session_id, response.text)
        yield WebSocketRequest(
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
        """Expose Demo request failures."""
        print(f"error output: {failure}")
        yield None
