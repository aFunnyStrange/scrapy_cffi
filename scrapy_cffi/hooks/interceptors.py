from typing import Protocol, Dict, TYPE_CHECKING
if TYPE_CHECKING:
    from ..core.sessions import SessionWrapper

class SessionHooks(Protocol):
    def acquire(self, session_id: str) -> None: ...

    def release(self, session_id: str) -> None: ...

    def get_or_create_session(self, session_id: str, cookies: Dict=None) -> "SessionWrapper": ...

class InterceptorsHooks(Protocol):
    session: SessionHooks
