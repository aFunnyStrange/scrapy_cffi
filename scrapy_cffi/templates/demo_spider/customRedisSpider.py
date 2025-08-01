from scrapy_cffi.spiders import RedisSpider
from scrapy_cffi.exceptions import Failure
from scrapy_cffi.internet import *

class CustomRedisSpider(RedisSpider):
    name = "customRedisSpider"
    robot_scheme = "http"
    allowed_domains = ["api.ipify.org", "127.0.0.1:8002", "localhost:8765"]
    redis_key = "customRedisSpider_test"
    count = 0
    'RPUSH customRedisSpider_test http://127.0.0.1:8002'

    async def parse(self, response: HttpResponse):
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
        print(f"spider received：{self.count}")
        if self.count < 3:
            print({"session_id": response.session_id, "data": response.msg[0].decode()})
            yield WebSocketRequest(
                session_id=self.session_id,
                websocket_id=response.websocket_id,
                send_message=f"hello：{self.count}".encode('utf-8')
            )
        elif self.count == 3:
            yield WebSocketRequest(
                session_id=self.session_id,
                websocket_id=response.websocket_id,
                websocket_end=True,
                # send_message=f"hello：{self.count}".encode('utf-8')
            )
            yield {"session_id": response.session_id, "data": response.msg[0].decode()}
            yield {"session_id": response.session_id, "data": "spider end"}
        self.count += 1

    async def errRet(self, failure: Failure):
        print(str(failure))
        yield None