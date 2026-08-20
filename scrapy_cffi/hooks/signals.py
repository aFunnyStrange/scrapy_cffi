from typing import Protocol, Callable, Any, TypeVar, Union, Awaitable, Optional

T = TypeVar("T")

class SignalHooks(Protocol):
    SignalCallback = Union[Callable[[T], Any], Callable[[T], Awaitable[Any]]]
    def connect(self, signal: object, callback: SignalCallback) -> None: ...

class SignalsHooks(Protocol):
    session: "SessionHooks"
    signals: SignalHooks


class SessionHooks(Protocol):
    def configure_rate_limit(
        self,
        session_id: str,
        requests_per_second: Optional[float],
    ) -> None: ...
