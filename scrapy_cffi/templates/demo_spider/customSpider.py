import random
from scrapy_cffi.utils import create_uniqueId
from scrapy_cffi.spiders import Spider
from scrapy_cffi.exceptions import Failure
from scrapy_cffi.internet import *
from items.item import CustomItem

class CustomSpider(Spider):
    name = "customSpider"
    robot_scheme = "http"
    allowed_domains = ["api.ipify.org", "127.0.0.1:8002", "localhost:8765"]
    start_urls = ["http://127.0.0.1:8002"]
    count = 0

    async def parse(self, response: HttpResponse):
        self.session_id = create_uniqueId()
        print(response.session_id, response.text)
        yield WebSocketRequest(
            session_id=self.session_id,
            url="ws://localhost:8765",
            headers=self.settings.DEFAULT_HEADERS,
            cookies=self.settings.DEFAULT_COOKIES,
            proxies=self.settings.PROXIES,
            timeout=self.settings.TIMEOUT,
            dont_filter=self.settings.DONT_FILTER,
            callback=self.sec_test, 
            errback=self.errRet,
            send_message=f"connect send test".encode('utf-8')
        )

    async def sec_test(self, response: WebSocketResponse):
        js_res = self.use_execjs(ctx_key="js_action", funcname="count", params=(self.count, random.random()))
        print(f"spider {self.name} callback received：{self.count}")
        if self.count < 3:
            print({"session_id": response.session_id, "data": response.msg[0].decode()})
            yield WebSocketRequest(
                session_id=self.session_id,
                websocket_id=response.websocket_id,
                send_message=f"hello：{self.count} -> {js_res}".encode('utf-8')
            )
        elif self.count == 3:
            yield WebSocketRequest(
                session_id=self.session_id,
                websocket_id=response.websocket_id,
                websocket_end=True,
                # send_message=f"hello：{self.count} -> {js_res}".encode('utf-8')
            )
            customItem = CustomItem() or {}
            customItem["session_id"] = response.session_id
            customItem["data"] = response.msg[0].decode()
            yield customItem

            customItem = CustomItem() or {}
            customItem["session_id"] = response.session_id
            customItem["session_end"] = True
            customItem["data"] = "spider end"
            yield customItem
            yield WebSocketRequest(
                session_id=self.session_id,
                websocket_id=response.websocket_id,
                send_message=f"retry after send session_end=True：{self.count} -> {js_res}".encode('utf-8')
            )
        self.count += 1

    async def errRet(self, failure: Failure):
        print(f'error output：{str(failure)}')
        yield None