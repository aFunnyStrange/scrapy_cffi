from typing import Protocol, TYPE_CHECKING, Dict
if TYPE_CHECKING:
    from ..extensions import SignalInfo

class SignalHooks(Protocol):
    def send(self, signal: object, data: "SignalInfo") -> None: ...

class _SessionHooks(Protocol):
    def mark_end(self, session_id: str) -> None: ...

    def get_session_cookies(self, session_id: str) -> Dict: ...

class SessionHooks(Protocol):
    def get_session_cookies(self, session_id: str) -> Dict: ...

class _PipelinesHooks(Protocol):
    session: _SessionHooks

class PipelinesHooks(Protocol):
    session: SessionHooks
    signals: SignalHooks