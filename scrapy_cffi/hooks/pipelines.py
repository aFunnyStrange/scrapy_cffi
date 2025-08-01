from typing import Protocol, Union, TYPE_CHECKING, Dict
if TYPE_CHECKING:
    from ..models.api import SingalInfo

class SignalHooks(Protocol):
    def send(self, signal: object, data: "SingalInfo") -> None: ...

class SessionHooks(Protocol):
    def mark_end(self, session_id: str) -> None: ...

    async def session_end_cookies(self, session_id: str) -> Union[Dict, None]: ...

class _PipelinesHooks(Protocol):
    session: SessionHooks

class PipelinesHooks(Protocol):
    signals: SignalHooks