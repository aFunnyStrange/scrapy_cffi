import asyncio, time
from ..extensions import signals, SignalInfo
from ..utils.concurrency import safe_call, CallFunction
from typing import TYPE_CHECKING, Callable, Dict, Optional, Set
if TYPE_CHECKING:
    from ..crawler import Crawler
    from ..settings import SettingsInfo
    from ..extensions import SignalManager
    from ..repo.queue import KafkaQueueRepository

class TaskManager:
    def __init__(
        self, 
        stop_event: asyncio.Event=None, 
        global_lock=None, 
        signalManager: "SignalManager"=None, 
        kafka_repository: "KafkaQueueRepository"=None,
        settings: "SettingsInfo"=None, 
        is_distributed=False
    ):
        self.stop_event = stop_event
        self.global_lock = global_lock

        from ..utils.log import init_logger
        self.logger = init_logger(log_info=settings.LOG_INFO, logger_name=__name__)
        if kafka_repository:
            from ..utils.log import KafkaLoggingHandler
            kafka_handler = KafkaLoggingHandler(kafka=kafka_repository, stop_event=self.stop_event).create_fmt(settings)
            self.logger.addHandler(kafka_handler)

        self.signalManager = signalManager
        self.active_tasks = 1 if is_distributed else 0
        self.active_task_names: Dict[str, int] = {}
        self.active_object_tasks: Dict[int, int] = {}
        self.object_idle_events: Dict[int, asyncio.Event] = {}
        self.object_activity_events: Dict[int, asyncio.Event] = {}
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
            kafka_repository=crawler.resources.kafka,
            settings=crawler.settings, 
            is_distributed=is_distributed
        )

    async def create(self, callfunc: "CallFunction", callback: Optional[Callable] = None, **callback_kwargs):
        if not isinstance(callfunc, CallFunction):
            raise TypeError("callfunc must be CallFunction instance")
        
        if self.stop_event.is_set():
            return
        callfunc_name = callfunc.get_func_name()
        obj_id = callfunc.obj_id

        async def wrapped():
            task_id = id(asyncio.current_task())
            async with self.global_lock():
                try:
                    self.logger.debug(f'add task {task_id} -> {self.active_tasks}：{callfunc_name}')
                    result = await callfunc.to_coro()
                    if callback:
                        await safe_call(callback, result, **callback_kwargs)
                except asyncio.CancelledError:
                    raise
                except KeyboardInterrupt:
                    self.error_event.set()
                    raise
                except Exception as e:
                    result = f"<Task-Error exception={repr(e)}>"
                    self.logger.error(result)
                    self.error_event.set()
                    self.signalManager.send(signal=signals.task_error, data=SignalInfo(signal_time=time.time(), reason=result))
                    raise ValueError(result)
                finally:
                    async with self.lock:
                        self.active_tasks -= 1
                        self.active_task_names[callfunc_name] = self.active_task_names.get(callfunc_name, 1) - 1
                        if self.active_task_names[callfunc_name] <= 0:
                            self.active_task_names.pop(callfunc_name, None)
                        self.logger.debug(f'end task {task_id} -> {self.active_tasks}：{callfunc_name}')
                        if self.active_tasks <= 0:
                            self.tasks_done_event.set()
                        if obj_id is not None:
                            self.active_object_tasks[obj_id] = (
                                self.active_object_tasks.get(obj_id, 1) - 1
                            )
                            if self.active_object_tasks[obj_id] <= 0:
                                self.active_object_tasks.pop(obj_id, None)
                                self.object_idle_events[obj_id].set()
                            self.object_activity_events.setdefault(
                                obj_id,
                                asyncio.Event(),
                            ).set()

        async with self.lock:
            self.active_tasks += 1
            self.active_task_names[callfunc_name] = self.active_task_names.get(callfunc_name, 0) + 1
            self.tasks_done_event.clear()
            if obj_id is not None:
                idle_event = self.object_idle_events.setdefault(
                    obj_id,
                    asyncio.Event(),
                )
                self.active_object_tasks[obj_id] = (
                    self.active_object_tasks.get(obj_id, 0) + 1
                )
                idle_event.clear()
                self.object_activity_events.setdefault(
                    obj_id,
                    asyncio.Event(),
                ).set()
        loop = asyncio.get_running_loop() # Obtain the event loop here to ensure this is called within an async context
        try:
            task = loop.create_task(wrapped())
        except Exception:
            async with self.lock:
                self.active_tasks -= 1
                self.active_task_names[callfunc_name] = self.active_task_names.get(callfunc_name, 1) - 1
                if self.active_task_names[callfunc_name] <= 0:
                    self.active_task_names.pop(callfunc_name, None)
                if self.active_tasks <= 0:
                    self.tasks_done_event.set()
                if obj_id is not None:
                    self.active_object_tasks[obj_id] = (
                        self.active_object_tasks.get(obj_id, 1) - 1
                    )
                    if self.active_object_tasks[obj_id] <= 0:
                        self.active_object_tasks.pop(obj_id, None)
                        self.object_idle_events[obj_id].set()
                    self.object_activity_events.setdefault(
                        obj_id,
                        asyncio.Event(),
                    ).set()
            raise
        self.managed_tasks.add(task)
        task.add_done_callback(self.managed_tasks.discard)
        return task

    async def wait_for_object_idle(self, obj_id: int) -> None:
        """Wait until one Engine has no managed task capable of producing work."""
        async with self.lock:
            if self.active_object_tasks.get(obj_id, 0) <= 0:
                return
            idle_event = self.object_idle_events.setdefault(
                obj_id,
                asyncio.Event(),
            )
        await idle_event.wait()

    async def wait_for_object_quiescent(
        self,
        obj_id: int,
        exclude_prefixes: tuple[str, ...] = (),
    ) -> None:
        """Wait for real task transitions until one Engine has no work tasks."""
        scope = f"[{obj_id}]"
        while True:
            async with self.lock:
                has_work = any(
                    count > 0
                    and scope in task_name
                    and not any(
                        task_name.startswith(prefix)
                        for prefix in exclude_prefixes
                    )
                    for task_name, count in self.active_task_names.items()
                )
                if not has_work:
                    return
                activity_event = self.object_activity_events.setdefault(
                    obj_id,
                    asyncio.Event(),
                )
                activity_event.clear()
            await activity_event.wait()

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

    async def has_active_tasks_except(self, name_prefix: str) -> bool:
        async with self.lock:
            for task_name, count in self.active_task_names.items():
                if count > 0 and not task_name.startswith(name_prefix):
                    return True
            return False

    async def has_active_tasks_for_obj(
        self,
        obj_id: int,
        exclude_prefixes: tuple[str, ...] = (),
    ) -> bool:
        scope = f"[{obj_id}]"
        async with self.lock:
            for task_name, count in self.active_task_names.items():
                if count <= 0:
                    continue
                if scope not in task_name:
                    continue
                if exclude_prefixes and any(task_name.startswith(p) for p in exclude_prefixes):
                    continue
                return True
            return False

    async def count_active_tasks_for_obj(
        self,
        obj_id: int,
        prefixes: tuple[str, ...] = (),
    ) -> int:
        scope = f"[{obj_id}]"
        total = 0
        async with self.lock:
            for task_name, count in self.active_task_names.items():
                if count <= 0:
                    continue
                if scope not in task_name:
                    continue
                if prefixes and (not any(task_name.startswith(p) for p in prefixes)):
                    continue
                total += count
        return total

    async def wait_for_object_task_count_below(
        self,
        obj_id: int,
        prefixes: tuple[str, ...],
        limit: int,
    ) -> None:
        """Wait for a task-completion event instead of polling capacity."""
        while True:
            async with self.lock:
                scope = f"[{obj_id}]"
                count = sum(
                    task_count
                    for task_name, task_count in self.active_task_names.items()
                    if task_count > 0
                    and scope in task_name
                    and any(task_name.startswith(prefix) for prefix in prefixes)
                )
                if count < limit:
                    return
                activity_event = self.object_activity_events.setdefault(
                    obj_id,
                    asyncio.Event(),
                )
                activity_event.clear()
            await activity_event.wait()

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
        current_task = asyncio.current_task()
        # all_tasks = asyncio.all_tasks()
        # cancel_targets = [t for t in all_tasks if t is not current_task and not t.done()]
        cancel_targets = [t for t in self.managed_tasks if t is not current_task and not t.done()]
        pending_names = [self.get_task_coro_path(t) for t in cancel_targets]
        self.logger.debug(f"Cancel tasks list: {pending_names}")

        for task in cancel_targets:
            task.cancel()
        await asyncio.sleep(0)
        self.logger.info(f"Cancelled {len(cancel_targets)} coroutine tasks")
        if cancel_targets:
            done, pending = await asyncio.wait(cancel_targets, timeout=3.0)
            for task in pending:
                self.logger.warning(f"Task did not finish after cancellation: {self.get_task_coro_path(task)}")
            for task in done:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    self.logger.error(f"Exception raised while cancelling task: {e}")
