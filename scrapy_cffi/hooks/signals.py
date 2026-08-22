"""Define the typed capabilities exposed to observation extensions."""

from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Optional,
    Protocol,
    TypeVar,
    Union,
)

if TYPE_CHECKING:
    from logging import Logger
    from ..settings import SettingsInfo

T = TypeVar("T")

class SignalHooks(Protocol):
    """Describe signal subscription available to an Extension."""

    SignalCallback = Union[Callable[[T], Any], Callable[[T], Awaitable[Any]]]

    def connect(self, signal: object, callback: SignalCallback) -> None:
        """Subscribe a callback to a signal identity."""
        ...

class SignalsHooks(Protocol):
    """Expose stable runtime context and signal/session capabilities."""

    settings: "SettingsInfo"
    logger: "Logger"
    session: "SessionHooks"
    signals: SignalHooks


class SessionHooks(Protocol):
    """Describe session controls made available to Extensions."""

    def configure_rate_limit(
        self,
        session_id: str,
        requests_per_second: Optional[float],
    ) -> None:
        """Configure the request-start rate for one session."""
        ...
