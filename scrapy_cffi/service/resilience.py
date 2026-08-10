"""Provide reusable retry and resource-replacement policy above infrastructure."""

import asyncio
import inspect
from typing import TYPE_CHECKING, Awaitable, Callable, Generic, Optional, Tuple, Type, TypeVar

if TYPE_CHECKING:
    from logging import Logger


T = TypeVar("T")
R = TypeVar("R")
AsyncOperation = Callable[[], Awaitable[R]]
AsyncRecovery = Callable[[], Awaitable[None]]


class ResourceSlot(Generic[T]):
    """Own one replaceable long-lived resource and serialize replacement."""

    def __init__(self, factory: Callable[[], T]) -> None:
        """Store a side-effect-free resource factory."""
        self._factory = factory
        self._resource: Optional[T] = None
        self._lock = asyncio.Lock()
        self._generation = 0

    @property
    def generation(self) -> int:
        """Return the current resource generation."""
        return self._generation

    def get(self) -> T:
        """Return the started resource or raise a lifecycle error."""
        if self._resource is None:
            raise RuntimeError("ResourceSlot has not been started")
        return self._resource

    async def start(self) -> None:
        """Construct and initialize the resource once."""
        async with self._lock:
            if self._resource is not None:
                return
            resource = self._factory()
            try:
                await self._call_optional(resource, "connect", "init")
            except BaseException:
                await self._close_failed_resource(resource)
                raise
            self._resource = resource

    async def replace(self, observed_generation: Optional[int] = None) -> None:
        """Replace a failed resource once for all concurrent observers."""
        async with self._lock:
            if observed_generation is not None and observed_generation != self._generation:
                return
            previous = self._resource
            self._resource = None
            if previous is not None:
                try:
                    await self._call_optional(previous, "close")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # A broken transport may also fail while closing. Recovery
                    # must still be able to construct a fresh generation.
                    pass
            replacement = self._factory()
            try:
                await self._call_optional(replacement, "connect", "init")
            except BaseException:
                await self._close_failed_resource(replacement)
                raise
            self._resource = replacement
            self._generation += 1

    async def close(self) -> None:
        """Close the current resource and make the slot unavailable."""
        async with self._lock:
            resource = self._resource
            self._resource = None
            if resource is not None:
                await self._call_optional(resource, "close")

    @staticmethod
    async def _call_optional(resource: T, *names: str) -> None:
        """Call the first available lifecycle method."""
        for name in names:
            method = getattr(resource, name, None)
            if method is None:
                continue
            result = method()
            if inspect.isawaitable(result):
                await result
            return

    @classmethod
    async def _close_failed_resource(cls, resource: T) -> None:
        """Best-effort close without hiding the original startup failure."""
        try:
            await cls._call_optional(resource, "close")
        except BaseException:
            pass


class RetryPolicy:
    """Run bounded retry and trigger injected resource replacement."""

    def __init__(
        self,
        stop_event: asyncio.Event,
        retry_exceptions: Tuple[Type[BaseException], ...],
        max_attempts: int = 3,
        retry_delay: float = 1.0,
        retry_predicate: Optional[Callable[[BaseException], bool]] = None,
        label: str = "resource",
        logger: Optional["Logger"] = None,
    ) -> None:
        """Configure bounded attempts without knowing any concrete client."""
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._stop_event = stop_event
        self._retry_exceptions = retry_exceptions
        self._max_attempts = max_attempts
        self._retry_delay = retry_delay
        self._retry_predicate = retry_predicate
        self._label = label
        self._logger = logger

    async def run(
        self,
        operation: AsyncOperation[R],
        recover: AsyncRecovery,
        allow_during_shutdown: bool = False,
    ) -> R:
        """Run one operation with bounded recovery between failed attempts."""
        for attempt in range(1, self._max_attempts + 1):
            if self._stop_event.is_set() and not allow_during_shutdown:
                raise asyncio.CancelledError("Runtime is stopping")
            try:
                return await operation()
            except asyncio.CancelledError:
                raise
            except self._retry_exceptions as exc:
                if self._retry_predicate is not None and not self._retry_predicate(exc):
                    raise
                if attempt >= self._max_attempts:
                    raise
                if self._logger is not None:
                    self._logger.warning(
                        "%s operation failed; replacing resource before retry %s/%s: %r",
                        self._label,
                        attempt + 1,
                        self._max_attempts,
                        exc,
                    )
                recovery_failures = 0
                while True:
                    try:
                        await recover()
                        break
                    except asyncio.CancelledError:
                        raise
                    except self._retry_exceptions as recovery_exc:
                        if (
                            self._retry_predicate is not None
                            and not self._retry_predicate(recovery_exc)
                        ):
                            raise
                        recovery_failures += 1
                        if attempt + recovery_failures >= self._max_attempts:
                            raise
                        if self._logger is not None:
                            self._logger.warning(
                                "%s replacement failed; retrying recovery %s/%s: %r",
                                self._label,
                                attempt + recovery_failures,
                                self._max_attempts,
                                recovery_exc,
                            )
                        if self._retry_delay:
                            await asyncio.sleep(self._retry_delay)
                if self._retry_delay:
                    await asyncio.sleep(self._retry_delay)
        raise RuntimeError("RetryPolicy exhausted without a result")


__all__ = ["ResourceSlot", "RetryPolicy"]
