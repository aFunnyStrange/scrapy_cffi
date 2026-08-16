"""Queue Demo spider covering event-driven WebSocket flows."""

import os

from demo_support.endpoints import DEMO_WS_URL
from scrapy_cffi.exceptions import Failure
from scrapy_cffi.internet import (
    CloseSignal,
    HttpResponse,
    WebSocketMsg,
    WebSocketRequest,
    WebSocketResponse,
)
from scrapy_cffi.spiders import RedisSpider
from scrapy_cffi.utils import create_uniqueId


class CustomRedisSpider(RedisSpider):
    """Exchange bounded frames over a long-lived WebSocket connection."""

    name = "customRedisSpider"
    robot_scheme = "http"
    allowed_domains = ["api.ipify.org", "127.0.0.1", "localhost"]
    redis_key = "customRedisSpider_test"
    # Normal verification receives one request and exits from a real producer
    # completion event. Continuous verification uses the same generated Spider.
    start_request_limit = (
        None
        if os.environ.get("SCRAPY_CFFI_DEMO_CONTINUOUS") == "1"
        else 1
    )
    async def parse(self, response: HttpResponse):
        """Connect and send the first frame without a separate request type."""
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
            send_message=WebSocketMsg(data=b"connect send test"),
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
                    data=next_message.encode("utf-8")
                ),
            )
        elif data.endswith("hello: 2"):
            response.stop_listening()
            yield {"session_id": response.session_id, "data": data}
            yield {"session_id": response.session_id, "data": "spider end"}
            yield CloseSignal(session_id=self.session_id, session_end=True)

    async def errRet(self, failure: Failure):
        """Expose Demo request failures."""
        print(str(failure))
        yield None
