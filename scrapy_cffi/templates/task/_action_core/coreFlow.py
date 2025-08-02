import asyncio, sys, random
from _action_core.coreBase import Base
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class BaseFlow(Base):
    async def some_flow_interface_1(self):
        """Scheduling the underlying logic for writing common processes"""
        some_base_interface_1_res = self.some_base_interface_1()
        if not some_base_interface_1_res.get("status"):
            return some_base_interface_1_res
        base_interface_1_data = some_base_interface_1_res.get("data", {}).get("response_data", -1)
        await asyncio.sleep(0.3)

        some_base_interface_2_res = self.some_base_interface_2()
        if not some_base_interface_2_res.get("status"):
            return some_base_interface_2_res
        base_interface_2_data = some_base_interface_2_res.get("data", {}).get("response_data", -1)
        await asyncio.sleep(0.3)
        res = random.randint(0, 1) # Simulation success/failure
        data = base_interface_1_data + base_interface_2_data - res
        if res:
            return {"status": res, "data": {"text": "some_flow_interface_1 sucess", "response_data": data}}
        return {"status": res, "data": {"text": "some_flow_interface_1 fail", "response_data": data}}

    async def some_flow_interface_2(self):
        """Scheduling the underlying logic for writing common processes"""
        some_base_interface_1_res = self.some_base_interface_1()
        if not some_base_interface_1_res.get("status"):
            return some_base_interface_1_res
        base_interface_1_data = some_base_interface_1_res.get("data", {}).get("response_data", -1)
        await asyncio.sleep(0.4)

        some_base_interface_2_res = self.some_base_interface_2()
        if not some_base_interface_2_res.get("status"):
            return some_base_interface_2_res
        base_interface_2_data = some_base_interface_2_res.get("data", {}).get("response_data", -1)
        await asyncio.sleep(0.2)
        res = random.randint(0, 1) # Simulation success/failure
        data = base_interface_1_data * base_interface_2_data - res
        if res:
            return {"status": res, "data": {"text": "some_flow_interface_2 sucess", "response_data": data}}
        return {"status": res, "data": {"text": "some_flow_interface_2 fail", "response_data": data}}