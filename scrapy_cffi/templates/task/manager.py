# 主控
import asyncio, sys, json
from scrapy_cffi.utils import get_run_py_dir, load_settings_from_py
from scrapy_cffi.utils import run_with_timeout
from spiders.runner import main as spiders_main
from _action_core import BaseManager
from component import *
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from curl_cffi.requests import Response
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from scrapy_cffi.utils import setup_uvloop_once
setup_uvloop_once()

class Manager(BaseManager):
    def __init__(self, log_name=""):
        # self.test_botton = 1 # 测试数据

        self.stop_event = asyncio.Event()
        self.task_queue = asyncio.Queue(maxsize=10)
        self.result_queue = asyncio.Queue(maxsize=500)
        self.init_info = load_settings_from_py(run_py_dir / "config.py", auto_upper=False)
        super().__init__(run_py_dir=run_py_dir, log_name=log_name, init_info=self.init_info)
        if self.redis_url:
            from scrapy_cffi.databases import RedisManager
            self.redis_manager = RedisManager(stop_event=self.stop_event, redis_url=self.redis_url)

    # 内部接口响应回调
    async def manager_inner_result(self, task: asyncio.Task, task_param: str="", data=None, fill_text: str="", error_retry=0):
        try:
            response: "Response" = task.result()
            response_json = response.json()
            self.logger.debug(f"{fill_text}接口响应：{response_json}")
        except Exception as e:
            self.logger.error(f"{fill_text}接口出错：{e}")
            if error_retry < 1:
                error_retry += 1
                await asyncio.sleep(10)
                if task_param:
                    task = asyncio.create_task(self.do_req(method="GET", url=self.join_url_params(self.get_task_url, params={"type": task_param, "platform": self.platform}), headers=self.headers, no_proxy=True))
                    task.add_done_callback(lambda t: asyncio.create_task(self.manager_inner_result(t, task_param=task_param, fill_text="获取任务", error_retry=error_retry)))
                elif data:
                    task = asyncio.create_task(self.do_req(method="POST", url=self.update_result_url, headers=self.headers, data=data, no_proxy=True))
                    task.add_done_callback(lambda t: asyncio.create_task(self.manager_inner_result(t, data=data, fill_text="任务回调更新", error_retry=error_retry)))
            return

        try:
            """
            # 测试数据
            # if not response_json.get("data", None):
            if self.test_botton:
                response_json = {'data': {'details': [{'small_task_id': 22, 'smail_task_type': 'smail_task_type', smail_task_info, ...}, {smail_task_2}, ...]}], 'platform': 0, 'task_id': 27, 'task_type': 'task_type'}, 'msg': '成功', 're_code': 0, 'success': True}
                self.test_botton = 0
            else:
                response_json = {"data": {"details": [], "platform": 0, "task_id": 17, "task_type": "task_type"}, "msg": "成功", "re_code": 0, "success": True}
            """
            all_task_data = response_json.get("data", None)
            if all_task_data and all_task_data.get("details"):
                await self.task_queue.put(all_task_data)
                # If there is a task of this task type, immediately add a request without waiting.
                task = asyncio.create_task(self.do_req(method="GET", url=self.join_url_params(self.get_task_url, params={"type": task_param, "platform": self.platform}), headers=self.headers, no_proxy=True))
                task.add_done_callback(lambda t, task_param=task_param: asyncio.create_task(self.manager_inner_result(t, task_param=task_param, fill_text="获取任务")))
        except Exception as e:
            self.logger.debug(f"获取任务响应内容解析出错：{e}，响应内容：{response.text}")

    async def producer(self):
        try:
            while not self.stop_event.is_set():
                for task_param in self.task_params:
                    task = asyncio.create_task(self.do_req(method="GET", url=self.join_url_params(self.get_task_url, params={"type": task_param, "platform": self.platform}), headers=self.headers, no_proxy=True))
                    task.add_done_callback(lambda t, task_param=task_param: asyncio.create_task(self.manager_inner_result(t, task_param=task_param, fill_text="获取任务")))
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise

    async def manager_result(self):
        try:
            while not self.stop_event.is_set():
                consumer_result_dict = await run_with_timeout(self.result_queue.get, stop_event=self.stop_event, timeout=5)
                result_list = consumer_result_dict.get("result_list", [])
                if result_list:
                    data = {
                        "status": "success" if consumer_result_dict.get("status") else "fail",
                        "task_id": consumer_result_dict.get("task_id", 0),
                        "task_type": consumer_result_dict.get("task_type", ""),
                        "data": result_list
                    }
                    self.logger.debug(f'任务回调更新的 data：{data}')
                    data = json.dumps(data, separators=(",", ":"))
                    task = asyncio.create_task(self.do_req(method="POST", url=self.update_result_url, headers=self.headers, data=data, no_proxy=True))
                    task.add_done_callback(lambda t, data=data: asyncio.create_task(self.manager_inner_result(t, data=data, fill_text="任务回调更新")))
                self.result_queue.task_done()
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise

    async def consumer(self):
        try:
            while not self.stop_event.is_set():
                all_task_data = await run_with_timeout(self.task_queue.get, stop_event=self.stop_event, timeout=5)
                if all_task_data.get("details", []):
                    consumer_obj = MidManager(
                        manager=self,
                        all_task_data=all_task_data,
                    )
                    consumer_result_dict = await consumer_obj.run_all_tasks()
                    if consumer_result_dict:
                        await self.result_queue.put(consumer_result_dict)
                self.task_queue.task_done()
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise

    async def start_engine(self):
        task_list = [
            asyncio.create_task(self.producer()),
            asyncio.create_task(self.manager_result()),
        ]
        for i in range(self.concurrent_quantity): # create many consumers and used await to limit
            task_list.append(asyncio.create_task(self.consumer()))

        if self.redis_url:
            # This will launch the redis-spider you have configured
            import multiprocessing
            multiprocessing.Process(target=spiders_main).start()
        await asyncio.gather(*task_list)

    def main(self):
        init_text = (
            f'\n{"—" * 180}\n' + 
            f"all tasks: {self.task_params}\n" + 
            f"concurrent_quantity: {self.concurrent_quantity}\n" +
            f"max_req_timeout: {self.max_req_timeout}\n" +
            f"proxies: {self.proxies}\n" +
            f"js files: {self.js_path}，目录下的文件：{list(self.ctx_dict.keys())}\n" +
            f"get task media url: {self.publish_baseurl}\n" +
            f"get task url: {self.get_task_url}\n" +
            f"update result url: {self.update_result_url}\n" +
            f"inner headers: {self.headers}\n" +
            f"redis url: {self.redis_url}\n" +
            f'{"—" * 180}\n' + 
            "程序初始化完成"
        )
        self.logger.debug(init_text)

        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.start_engine())
        except KeyboardInterrupt as e:
            self.logger.debug("检测到按键退出，程序退出...")
            self.stop_event.set()
            # sometimes cannot be cleaned thoroughly.
            from scrapy_cffi.utils import cancel_all_tasks
            loop.run_until_complete(cancel_all_tasks())

if __name__ == "__main__":
    """debug with manager here"""
    run_py_dir = get_run_py_dir()
    Manager(log_name="my_project").main()