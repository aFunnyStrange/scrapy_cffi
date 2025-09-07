from typing import Protocol, TYPE_CHECKING, Dict
if TYPE_CHECKING:
    from ..models.api import SingalInfo

class SignalHooks(Protocol):
    def send(self, signal: object, data: "SingalInfo") -> None: ...

class SessionHooks(Protocol):
    def mark_end(self, session_id: str) -> None: ...

    def get_session_cookies(self, session_id: str) -> Dict: ...

class _PipelinesHooks(Protocol):
    session: SessionHooks

class PipelinesHooks(Protocol):
    signals: SignalHooks