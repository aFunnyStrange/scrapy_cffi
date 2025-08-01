import asyncio, sys, random
from utils import *
from _action_core import BaseFlow
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from scrapy_cffi.databases import RedisManager
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class CollectBase(BaseFlow):
    def __init__(self, 
            run_py_dir="", publish_baseurl="",
            cookies_dict={}, max_req_timeout=10, proxies=None, max_fail_count=5, ctx_dict={},
            redis: "RedisManager"=None
        ):
        super().__init__(
            run_py_dir=run_py_dir, publish_baseurl=publish_baseurl,
            cookies_dict=cookies_dict, max_req_timeout=max_req_timeout, proxies=proxies, max_fail_count=max_fail_count, ctx_dict=ctx_dict
        )
        self.redis = redis

    async def collect_base_interface(self):
        await asyncio.sleep(0.1)
        res = random.randint(0, 1) # 模拟成功/失败
        if res:
            return {"status": res, "data": {"text": "collect_base_interface sucess", "response_data": random.randint(50, 100)}}
        return {"status": res, "data": {"text": "collect_base_interface fail", "response_data": random.randint(10, 50)}}