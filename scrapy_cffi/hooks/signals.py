from typing import Protocol, Callable, Any, TypeVar, Union, Awaitable

T = TypeVar("T")

class SignalHooks(Protocol):
    SignalCallback = Union[Callable[[T], Any], Callable[[T], Awaitable[Any]]]
    def connect(self, signal: object, callback: SignalCallback) -> None: ...

class SignalsHooks(Protocol):
    signals: SignalHooks
