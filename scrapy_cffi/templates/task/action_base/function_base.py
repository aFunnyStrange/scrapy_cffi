import asyncio, sys, uuid, random
from utils import *
from _action_core import BaseFlow
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class FunctionBase(BaseFlow):
    def __init__(self, 
            run_py_dir="", publish_baseurl="",
            cookies_dict={}, max_req_timeout=10, proxies=None, max_fail_count=5, ctx_dict={}
        ):
        super().__init__(
            run_py_dir=run_py_dir, publish_baseurl=publish_baseurl,
            cookies_dict=cookies_dict, max_req_timeout=max_req_timeout, proxies=proxies, max_fail_count=max_fail_count, ctx_dict=ctx_dict
        )
        self.functionBase_data = str(uuid.uuid4())
        
    async def action_port_1(self):
        """
        用于编写实现某个功能的所有接口
        """
        await asyncio.sleep(0.1)
        res = random.randint(0, 1) # 模拟成功/失败
        if res:
            return {"status": res, "data": {"text": "some_base_interface_1 sucess", "response_data": self.functionBase_data}}
        return {"status": res, "data": {"text": "some_base_interface_1 fail", "response_data": 0}}
    
    async def action_port_2(self):
        """
        用于编写实现某个功能的所有接口
        """
        await asyncio.sleep(0.1)
        res = random.randint(0, 1) # 模拟成功/失败
        if res:
            return {"status": res, "data": {"text": "some_base_interface_1 sucess", "response_data": self.functionBase_data}}
        return {"status": res, "data": {"text": "some_base_interface_1 fail", "response_data": 0}}