import asyncio, time
from ..extensions import signals
from ..models.api import SingalInfo
from typing import TYPE_CHECKING, Coroutine, Callable, Optional, Set
if TYPE_CHECKING:
    from ..crawler import Crawler
    from ..models.api import SettingsInfo
    from ..extensions import SignalManager

class TaskManager:
    def __init__(self, stop_event: asyncio.Event=None, global_lock=None, signalManager: "SignalManager"=None, settings: "SettingsInfo"=None, is_distributed=False):
        self.stop_event = stop_event
        self.global_lock = global_lock
        from ..utils import init_logger
        self.logger = init_logger(log_info=settings.LOG_INFO, logger_name=__name__)
        self.signalManager = signalManager
        self.active_tasks = 1 if is_distributed else 0
        self.managed_tasks: Set[asyncio.Task] = set()
        self.tasks_done_event = asyncio.Event()
        self.error_event = asyncio.Event()
        self.lock = asyncio.Lock()
        self.tasks_done_event.set()

    @classmethod
    def from_crawler(cls, crawler: "Crawler", is_distributed=None):
        return cls(
            stop_event=crawler.stop_event,
            global_lock=crawler.global_lock,
            signalManager=crawler.signalManager, 
            settings=crawler.settings, 
            is_distributed=is_distributed
        )

    async def create(self, coro: Coroutine, callback: Optional[Callable] = None, **callback_kwargs):
        if self.stop_event.is_set():
            return

        async def wrapped():
            async with self.global_lock():
                try:
                    self.logger.debug(f'add task {task_id} -> {self.active_tasks}：{coro}')
                    result = await coro
                    if callback:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(result,**callback_kwargs)
                        elif asyncio.iscoroutine(callback):
                            self.logger.error(f"Coroutine object was mistakenly passed as a callback：{coro} -> {callback}")
                            await callback
                        else:
                            callback(result, **callback_kwargs)
                except asyncio.CancelledError:
                    if coro and asyncio.iscoroutine(coro):
                        coro.close()
                        self.error_event.set()
                    raise
                except Exception as e:
                    result = f"<Task-Error exception={repr(e)}>"
                    self.logger.error(result)
                    self.error_event.set()
                    self.signalManager.send(signal=signals.task_error, data=SingalInfo(signal_time=time.time(), reason=result))
                    raise ValueError(result)
                finally:
                    async with self.lock:
                        self.active_tasks -= 1
                        self.logger.debug(f'end task {task_id} -> {self.active_tasks}：{coro}')
                        if self.active_tasks <= 0:
                            self.tasks_done_event.set()

        loop = asyncio.get_running_loop() # Obtain the event loop here to ensure this is called within an async context
        task = loop.create_task(wrapped())
        task.add_done_callback(self.managed_tasks.discard)
        task_id = id(task)
        async with self.lock:
            self.active_tasks += 1
            self.tasks_done_event.clear()
        return task

    async def wait_until_stopped(self) -> str:
        tasks_done_task = asyncio.create_task(self.tasks_done_event.wait())
        error_task = asyncio.create_task(self.error_event.wait())
        done, pending = await asyncio.wait(
            [tasks_done_task, error_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return "error" if error_task in done else "tasks_done"

    def get_task_coro_path(self, task: asyncio.Task):
        try:
            coro = task.get_coro()
            if hasattr(coro, '__qualname__'):
                func_name = coro.__qualname__
            else:
                func_name = type(coro).__name__

            module = getattr(coro, '__module__', None)
            filename = getattr(coro.cr_code, 'co_filename', None) if hasattr(coro, 'cr_code') else None
            lineno = getattr(coro.cr_frame, 'f_lineno', None) if hasattr(coro, 'cr_frame') and coro.cr_frame else None

            parts = []
            if module:
                parts.append(f"{module}")
            if filename:
                parts.append(f"{filename}")
            parts.append(func_name)
            if lineno:
                parts.append(f":{lineno}")
            return " -> ".join(parts)
        except Exception as e:
            return f"<Unknown Task: {repr(e)}>"

    async def cancel_all(self):
        self.logger.info("Cancel all tasks ...")
        # current_task = asyncio.current_task()
        # all_tasks = asyncio.all_tasks()
        # cancel_targets = [t for t in all_tasks if t is not current_task and not t.done()]
        cancel_targets = [t for t in self.managed_tasks if not t.done()]
        pending_names = [self.get_task_coro_path(t) for t in cancel_targets]
        self.logger.debug(f"Cancel tasks list: {pending_names}")

        for task in cancel_targets:
            task.cancel()
        await asyncio.sleep(0)
        self.logger.info(f"Cancelled {len(cancel_targets)} coroutine tasks")
        for task in cancel_targets:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.logger.error(f"Exception raised while cancelling task: {e}")