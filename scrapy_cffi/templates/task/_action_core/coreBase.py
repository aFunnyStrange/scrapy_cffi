import asyncio, sys, random
from utils import *
from _action_core.reqBase import ReqBase
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class Base(ReqBase):
    def __init__(self, 
            run_py_dir="", publish_baseurl="",
            cookies_dict={}, max_req_timeout=10, proxies=None, max_fail_count=5, ctx_dict={}
        ):
        super().__init__(run_py_dir=run_py_dir, cookies_dict=cookies_dict, proxies=proxies, max_req_timeout=max_req_timeout, max_fail_count=max_fail_count, ctx_dict=ctx_dict)
        self.publish_baseurl = publish_baseurl

    async def some_base_interface_1(self):
        """
        调度底层的逻辑，用于编写公共的接口
        """
        await asyncio.sleep(0.1)
        res = random.randint(0, 1) # 模拟成功/失败
        if res:
            return {"status": res, "data": {"text": "some_base_interface_1 sucess", "response_data": 1}}
        return {"status": res, "data": {"text": "some_base_interface_1 fail", "response_data": 0}}

    async def some_base_interface_2(self):
        """
        调度底层的逻辑，用于编写公共的接口
        """
        await asyncio.sleep(0.5)
        res = random.randint(0, 1) # 模拟成功/失败
        if res:
            return {"status": res, "data": {"text": "some_base_interface_1 sucess", "response_data": 2}}
        return {"status": res, "data": {"text": "some_base_interface_1 fail", "response_data": 3}}