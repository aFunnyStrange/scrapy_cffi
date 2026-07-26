from scrapy_cffi.spiders import RedisSpider
from scrapy_cffi.exceptions import Failure
from scrapy_cffi.internet import (
    CloseSignal,
    HttpResponse,
    WebSocketMsg,
    WebSocketRequest,
    WebSocketResponse,
)
from demo_support.endpoints import DEMO_WS_URL

class CustomRedisSpider(RedisSpider):
    name = "customRedisSpider"
    robot_scheme = "http"
    allowed_domains = ["api.ipify.org", "127.0.0.1", "localhost"]
    redis_key = "customRedisSpider_test"
    count = 0

    async def parse(self, response: HttpResponse):
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
            send_message=WebSocketMsg(data=b"connect send test")
        )

    async def sec_test(self, response: WebSocketResponse):
        print(f"spider received：{self.count}")
        if self.count < 3:
            print({"session_id": response.session_id, "data": response.msg[0].decode()})
            yield WebSocketRequest(
                session_id=self.session_id,
                websocket_id=response.websocket_id,
                send_message=WebSocketMsg(data=f"hello：{self.count}".encode('utf-8'))
            )
        elif self.count == 3:
            yield CloseSignal(
                session_id=self.session_id,
                websocket_end_for_key=response.websocket_id,
            )
            yield {"session_id": response.session_id, "data": response.msg[0].decode()}
            yield {"session_id": response.session_id, "data": "spider end"}
        self.count += 1

    async def errRet(self, failure: Failure):
        print(str(failure))
        yield None
