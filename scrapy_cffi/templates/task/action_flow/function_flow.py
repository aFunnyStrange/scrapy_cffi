import asyncio, sys, random, uuid
from utils import *
from action_base import FunctionBase
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class FunctionFlow(FunctionBase):
    async def action_flow(self):
        """Simulate some pre operations for creating spider tasks, such as data validation and data generation"""
        some_base_interface_1_res = await self.some_base_interface_1()
        if not some_base_interface_1_res.get("status"):
            return some_base_interface_1_res
        base_interface_1_data = some_base_interface_1_res.get("data", {}).get("response_data", -1)
        await asyncio.sleep(3)

        some_base_interface_2_res = await self.some_base_interface_2()
        if not some_base_interface_2_res.get("status"):
            return some_base_interface_2_res
        base_interface_2_data = some_base_interface_2_res.get("data", {}).get("response_data", -1)
        await asyncio.sleep(3)

        data = base_interface_1_data * random.randint(50, 100) + base_interface_2_data * random.randint(1, 50)
        await asyncio.sleep(3)
        res = random.randint(0, 1) # Simulation success/failure
        if res:
            data = f"{uuid.uuid4()}|{data}|{self.functionBase_data}"
            return {"status": res, "data": {"text": "create_collect_task_flow sucess", "response_data": data}}
        data = f"{self.functionBase_data}|{data}"
        return {"status": res, "data": {"text": "create_collect_task_flow fail", "response_data": data}}
