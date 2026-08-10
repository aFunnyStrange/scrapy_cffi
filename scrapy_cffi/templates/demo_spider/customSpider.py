import random
from scrapy_cffi.platform import WebSocketFlag
from scrapy_cffi.utils import create_uniqueId
from scrapy_cffi.spiders import Spider
from scrapy_cffi.exceptions import Failure
from scrapy_cffi.internet import (
    CloseSignal,
    HttpResponse,
    WebSocketMsg,
    WebSocketRequest,
    WebSocketResponse,
)
from items.item import CustomItem
from demo_support.endpoints import DEMO_HTTP_URL, DEMO_WS_URL

class CustomSpider(Spider):
    name = "customSpider"
    robot_scheme = "http"
    allowed_domains = ["api.ipify.org", "127.0.0.1", "localhost"]
    start_urls = [DEMO_HTTP_URL]
    count = 0

    async def parse(self, response: HttpResponse):
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
            ping_data=WebSocketMsg(data="ping"),
        )

    async def sec_test(self, response: WebSocketResponse):
        js_res = self.use_execjs(ctx_key="js_action", funcname="count", params=(self.count, random.random()))
        print(f"spider {self.name} callback received：{self.count}")
        if self.count < 3:
            print({"session_id": response.session_id, "data": response.msg[0].decode()})
            yield WebSocketRequest(
                session_id=self.session_id,
                websocket_id=response.websocket_id,
                send_message=WebSocketMsg(data=f"hello：{self.count} -> {js_res}".encode('utf-8'), flags=WebSocketFlag.BINARY)
            )
        elif self.count == 3:
            yield CloseSignal(
                session_id=self.session_id,
                websocket_end_for_key=response.websocket_id,
            )
            customItem = CustomItem() or {}
            customItem["session_id"] = response.session_id
            customItem["data"] = response.msg[0].decode()
            yield customItem

            customItem = CustomItem() or {}
            customItem["session_id"] = response.session_id
            # customItem["session_end"] = True # scrapy_cffi version 0.1.x
            customItem["data"] = "spider end"
            yield customItem
            yield CloseSignal(session_id=self.session_id, session_end=True)
            yield WebSocketRequest(
                session_id=self.session_id,
                websocket_id=response.websocket_id,
                send_message=WebSocketMsg(data=f"retry after send session_end=True：{self.count} -> {js_res}".encode('utf-8'), flags=WebSocketFlag.BINARY)
            )
        self.count += 1

    async def errRet(self, failure: Failure):
        print(f'error output：{str(failure)}')
        yield None
