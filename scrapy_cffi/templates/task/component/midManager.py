# Central control, handling sub tasks out of order, and consolidating major tasks in a unified manner
import asyncio
from export_interface import *
from _action_core.reqBase import ReqBase
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from manager import Manager

class MidManager(ReqBase): # use the same info from manager, so didn't extends BaseManager
    def __init__(self, manager: "Manager", all_task_data={}):
        super().__init__(run_py_dir=manager.run_py_dir, proxies=manager.proxies, max_req_timeout=manager.max_req_timeout, redis_url=manager.redis_url, ctx_dict=manager.ctx_dict)
        self.sem = manager.sem
        self.publish_baseurl = manager.publish_baseurl
        self.redis_manager = manager.redis_manager
        self.consumer_result_dict = {
            "status": 0,
            "task_id": all_task_data.get("task_id", 0),
            "task_type": all_task_data.get("task_type", 0),
            "platform": all_task_data.get("platform", 0),
            "result_list": []
        }
        self.task_list = all_task_data.get("details", [])
        self.consumer_result_list = []
        
    async def run_all_tasks(self):
        self.consumer_result_list = await asyncio.gather(*[
            self.fetch_task(task_data) for task_data in self.task_list
        ])
        self.consumer_result_dict["result_list"] = self.consumer_result_list
        self.consumer_result_list = [it for it in self.consumer_result_list if it is not None] # Collect independently and return, remove the collection status
        for result in self.consumer_result_list:
            if result and (not result.get("status")):
                return self.consumer_result_dict # status = 0
        else:
            self.consumer_result_dict["status"] = 1
            return self.consumer_result_dict
    
    async def fetch_task(self, task_data):
        async with self.sem:
            try:
                single_result = {
                    "status": 0, 
                    "data": {"text": "There is an unknown branch in task scheduling", "response_data": ""}, 
                    "cookie_dict": task_data.get("cookie_dict", {}),
                    "task_id": self.consumer_result_dict.get("task_id", 0),
                    "small_task_id": task_data.get("small_task_id", 0),
                    "task_type": self.consumer_result_dict.get("task_type", 0),
                    "platform": self.consumer_result_dict.get("platform", 0)
                }
                if task_data.get("cookie_dict", {}) is None:
                    single_result["data"]["text"] = "The cookie for this account is None"
                else:
                    task_type = task_data.get("smail_task_type", self.consumer_result_dict.get("task_type", 0)) # Small task type
                    update_dict = {
                        "task_id": self.consumer_result_dict.get("task_id", 0),
                        "small_task_id": task_data.get("small_task_id", 0),
                        "task_type": self.consumer_result_dict.get("task_type", 0),
                        "small_task_type": task_type,
                        "platform": self.consumer_result_dict.get("platform", 0)
                    }
                    init_data={
                        "cookies_dict": task_data.get("cookie_dict", {}), 
                        "max_req_timeout": task_data.get("max_req_timeout", 90),
                        "proxies": task_data.get("proxies", None),
                        "publish_baseurl": self.publish_baseurl
                    }
                    if task_type == "some_action":
                        """
                        Suggest wrapping the instance of the class and the behavior of the object through this instance into a function, 
                        so that if necessary, you can also create child threads, child processes, or new loop here.
                        example:
                            from scrapy_cffi import run_coroutine_in_thread
                            single_result = await run_coroutine_in_thread(do_func(init_data=init_data))
                        """
                        single_result = await do_func(init_data=init_data)
                    elif task_type in ["school_collect", "teacher_collect", "student_collect"]:
                        # here just return the create collect task status, collect data come from spiders, it's mean need own server cooperation.
                        init_data["redis"] = self.redis_manager
                        single_result = await do_collect(init_data=init_data)
                    else:
                        single_result["data"]["text"] = "There is no such task type available"
                    single_result.update(update_dict) 
                return single_result
            except Exception as e:
                single_result["data"]["text"] = f"Subtask scheduling error: {e}"
                return single_result