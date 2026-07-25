import asyncio
from functools import wraps
from typing import Any, Awaitable, Callable, Optional, Tuple, Type, TypeVar, cast


AsyncCallable = Callable[[], Awaitable[Any]]
AsyncMethod = TypeVar("AsyncMethod", bound=Callable[..., Awaitable[Any]])


class AsyncReconnectController:
    """Coordinate retry/reconnect without changing a manager's public API.

    A generation counter collapses a burst of concurrent connection failures into
    one reconnect. Callers that observed the old generation simply reuse the
    connection rebuilt by the first caller.
    """

    def __init__(
        self,
        stop_event: asyncio.Event,
        reconnect: AsyncCallable,
        retry_exceptions: Tuple[Type[BaseException], ...],
        *,
        label: str,
        retry_delay: float = 1.0,
        max_attempts: Optional[int] = None,
        retry_predicate: Optional[Callable[[BaseException], bool]] = None,
    ):
        self._stop_event = stop_event
        self._reconnect = reconnect
        self._retry_exceptions = retry_exceptions
        self._label = label
        self._retry_delay = retry_delay
        self._max_attempts = max_attempts
        self._retry_predicate = retry_predicate
        self._lock = asyncio.Lock()
        self._generation = 0

    @property
    def generation(self) -> int:
        return self._generation

    def _ensure_running(self) -> None:
        if self._stop_event.is_set():
            raise asyncio.CancelledError(
                "Stop event set, abort %s operation" % self._label
            )

    async def run(
        self,
        operation: AsyncCallable,
        *,
        allow_during_shutdown: bool = False,
    ) -> Any:
        attempts = 0
        while True:
            if not allow_during_shutdown:
                self._ensure_running()
            observed_generation = self._generation
            try:
                return await operation()
            except self._retry_exceptions as exc:
                if self._retry_predicate is not None and not self._retry_predicate(exc):
                    raise
                attempts += 1
                if not allow_during_shutdown:
                    self._ensure_running()
                if self._max_attempts is not None and attempts >= self._max_attempts:
                    raise
                try:
                    await self._reconnect_once(observed_generation)
                except self._retry_exceptions:
                    if self._max_attempts is not None and attempts >= self._max_attempts:
                        raise
                    if self._retry_delay:
                        await asyncio.sleep(self._retry_delay)

    async def _reconnect_once(self, observed_generation: int) -> None:
        async with self._lock:
            if observed_generation != self._generation:
                return
            self._ensure_running()
            await self._reconnect()
            self._generation += 1

    async def recover(self, observed_generation: Optional[int] = None) -> None:
        """Reconnect explicitly after an error raised by a long-running loop."""
        if observed_generation is None:
            observed_generation = self._generation
        attempts = 0
        while True:
            self._ensure_running()
            try:
                await self._reconnect_once(observed_generation)
                return
            except self._retry_exceptions:
                attempts += 1
                if self._max_attempts is not None and attempts >= self._max_attempts:
                    raise
                if self._retry_delay:
                    await asyncio.sleep(self._retry_delay)


def reconnectable(func: AsyncMethod) -> AsyncMethod:
    """Route one explicit manager method through its reconnect controller."""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        controller = self._reconnect_controller
        return await controller.run(lambda: func(self, *args, **kwargs))

    return cast(AsyncMethod, wrapper)


__all__ = ["AsyncReconnectController", "reconnectable"]
