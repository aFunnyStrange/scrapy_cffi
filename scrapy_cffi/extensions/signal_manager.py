import asyncio
from collections import defaultdict
# from ..utils import run_with_timeout
from typing import Set, TYPE_CHECKING, Callable, Any, TypeVar, Union, Awaitable
if TYPE_CHECKING:
    from ..crawler import Crawler
    from ..models.api import SettingsInfo, SingalInfo

T = TypeVar("T")

class SignalManager:
    SignalCallback = Union[Callable[[T], Any], Callable[[T], Awaitable[Any]]]

    def __init__(self, stop_event=None, settings: "SettingsInfo"=None, maxsize=1000):
        from ..utils import init_logger
        self.logger = init_logger(log_info=settings.LOG_INFO, logger_name=__name__)
        self._listeners = defaultdict(list)
        self._queue = asyncio.Queue(maxsize=maxsize)
        self.stop_event: asyncio.Event = stop_event
        self._run_task = None
        self._pending_tasks: Set[asyncio.Task] = set()

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event, 
            settings=crawler.settings
        )

    def connect(self, signal: object, callback: SignalCallback):
        if not callable(callback):
            raise TypeError(f"Signal callback must be callable: got {type(callback)}")
        self._listeners[signal].append(callback)

    def send(self, signal: object, data: "SingalInfo"):
        if self.stop_event.is_set() or (not self._listeners[signal]):
            return
        asyncio.create_task(self._safe_put(signal, data))

    async def _safe_put(self, signal, data):
        if not self._listeners[signal]:
            return
        try:
            self._queue.put_nowait((signal, data))
        except asyncio.QueueFull:
            try:
                await asyncio.wait_for(self._queue.put((signal, data)), timeout=0.1)
            except asyncio.TimeoutError:
                self.logger.warning(f"[SignalManager] Signal queue full, dropped signal: {signal}")

    async def _dispatch(self, signal, data):
        for callback in self._listeners[signal]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    task = asyncio.create_task(callback(data))
                    self._pending_tasks.add(task)
                    task.add_done_callback(lambda t: self._pending_tasks.discard(t))
                else:
                    callback(data)
            except Exception as e:
                self.logger.error(f"[SignalManager] Signal callback error: {e}")

    async def run(self):
        try:
            while not self.stop_event.is_set():
                # signal, data = await run_with_timeout(self._queue.get, stop_event=self.stop_event, timeout=0.2)
                signal, data = await self._queue.get()
                if signal is not None:
                    await self._dispatch(signal, data)
        except asyncio.CancelledError:
            self.logger.warning("[SignalManager] run task cancelled, waiting for pending callbacks...")
            for task in self._pending_tasks:
                task.cancel()
            await asyncio.sleep(0)

            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._pending_tasks, return_exceptions=True),
                    timeout=3.0
                )
            except asyncio.TimeoutError:
                self.logger.warning("[SignalManager] Pending signal callbacks did not finish in time, force exit.")
            finally:
                raise

    def start(self):
        if not self._run_task or self._run_task.done():
            self._run_task = asyncio.create_task(self.run())

    async def stop(self):
        try:
            self._queue.put_nowait((None, None))
        except asyncio.QueueFull:
            pass

        if self._run_task:
            try:
                await asyncio.wait_for(self._run_task, timeout=3.0)
            except asyncio.TimeoutError:
                pass

        if self._pending_tasks:
            self.logger.info(f"[SignalManager] Waiting for {len(self._pending_tasks)} pending signal callback tasks to finish")
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)