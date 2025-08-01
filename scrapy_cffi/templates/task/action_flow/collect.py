import asyncio, sys, random, json
from utils import *
from scrapy_cffi.internet import HttpRequest
from action_base import CollectBase
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class CollectFlow(CollectBase):
    async def create_collect_task_flow(self):
        """Simulate some pre operations for creating spider tasks, such as data validation and data generation"""
        some_base_interface_1_res = await self.some_base_interface_1()
        if not some_base_interface_1_res.get("status"):
            return some_base_interface_1_res
        base_interface_1_data = some_base_interface_1_res.get("data", {}).get("response_data", -1)
        await asyncio.sleep(3)

        collect_base_interface_res = await self.collect_base_interface()
        if not collect_base_interface_res.get("status"):
            return collect_base_interface_res
        collect_base_interface_data = collect_base_interface_res.get("data", {}).get("response_data", -1)
        await asyncio.sleep(3)
        res = random.randint(0, 1) # 模拟成功/失败
        if res:
            task_data = {
                "cookies_dict": self.cookies_dict,
                "random_seed": random.random(),
                "check_data": f'{base_interface_1_data}|{collect_base_interface_data}'
            }
            if self.redis:
                # If the crawler is a continuously listening crawler that cannot be exited, then you need to add a task to your redis_key.
                # await self.redis.lpush("demo_redis", json.dumps(task_data, separators=(",", ":")))
                # request = HttpRequest(
                #     url="http://127.0.0.1:8002",
                #     task_data=task_data
                # )
                await self.redis.lpush("customRedisSpider_test", "http://127.0.0.1:8002".encode("utf-8"))
            return {"status": res, "data": {"text": "create_collect_task_flow sucess", "response_data": task_data}}
        return {"status": res, "data": {"text": "create_collect_task_flow fail", "response_data": base_interface_1_data}}
