import asyncio, sys
from _action_core.reqBase import ReqBase
from utils.common import init_logger # Absolute path import
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pathlib import Path

class BaseManager(ReqBase):
    def __init__(self, run_py_dir: "Path"=None, log_name="", init_info=None):
        self.run_py_dir = run_py_dir
        concurrent_quantity = init_info.get('concurrent_quantity', 100)
        max_req_timeout = init_info.get('max_req_timeout', 10)
        proxies = init_info.get('proxies')
        redis_url = init_info.get('redis_url', "")
        super().__init__(run_py_dir=self.run_py_dir, concurrent_quantity=concurrent_quantity, proxies=proxies, max_req_timeout=max_req_timeout, redis_url=redis_url)
        self.platform = init_info.get('platform')
        self.log_level = init_info.get('log_level', "DEBUG")
        self.task_params = init_info.get('task_params', [])
        self.publish_baseurl = init_info.get('publish_baseurl', "")
        self.get_task_url = init_info.get('get_task_url', "")
        self.update_result_url = init_info.get('update_result_url', "")
        self.headers = init_info.get('headers', {})
        self.redis_manager = None
        self.log_name = log_name
        self.logger = init_logger(
            run_py_dir=self.run_py_dir, 
            log_name=self.log_name if self.log_name else __name__, 
            log_level=self.log_level, 
            log_dir=self.log_name if self.log_name != "my_project" else ""
        )