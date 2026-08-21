"""Run short, awaited callables in a lazily started process pool."""

import asyncio
import inspect
import threading
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import Any, Callable, Dict, Optional, Set


class ProcessTaskError(RuntimeError):
    """Report invalid use of the crawler's short-task process pool."""


def _execute_process_call(func: Callable[..., Any], kwargs: Dict[str, Any]) -> Any:
    """Execute one picklable callable inside a worker process."""
    result = func(**kwargs)
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


class ProcessTaskManager:
    """Own a bounded process pool that starts only after the first submission.

    Submitted functions and arguments must be picklable. Callers should await
    short tasks; long-running services remain application-entrypoint concerns.
    """

    def __init__(self, max_workers: int = 2) -> None:
        """Configure the worker bound without creating an executor or process."""
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        self.max_workers = max_workers
        self._executor: Optional[ProcessPoolExecutor] = None
        self._executor_lock = threading.Lock()
        self._pending: Set[asyncio.Future] = set()
        self._closed = False

    @property
    def started(self) -> bool:
        """Return whether a submission has created the executor."""
        return self._executor is not None

    @property
    def pending_count(self) -> int:
        """Return the number of submitted calls not yet completed."""
        return len(self._pending)

    async def run(self, func: Callable[..., Any], **kwargs: Any) -> Any:
        """Submit and await one short picklable callable."""
        if not callable(func):
            raise TypeError("func must be callable")
        executor = self._get_executor()
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            executor,
            partial(_execute_process_call, func, kwargs),
        )
        self._pending.add(future)
        future.add_done_callback(self._pending.discard)
        try:
            return await future
        except asyncio.CancelledError:
            future.cancel()
            raise

    async def close(self) -> None:
        """Cancel queued work and wait for already running short calls to exit."""
        with self._executor_lock:
            if self._closed:
                return
            self._closed = True
            executor = self._executor
            self._executor = None
        if executor is not None:
            await asyncio.to_thread(
                executor.shutdown,
                wait=True,
                cancel_futures=True,
            )
        self._pending.clear()

    def _get_executor(self) -> ProcessPoolExecutor:
        """Create the process executor exactly once on first submission."""
        with self._executor_lock:
            if self._closed:
                raise ProcessTaskError("ProcessTaskManager is closed")
            if self._executor is None:
                self._executor = ProcessPoolExecutor(
                    max_workers=self.max_workers,
                )
            return self._executor


__all__ = ["ProcessTaskError", "ProcessTaskManager"]
