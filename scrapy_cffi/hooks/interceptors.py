from typing import Protocol, Dict, TYPE_CHECKING, Optional
if TYPE_CHECKING:
    from ..core.sessions import SessionWrapper

class SessionHooks(Protocol):
    def acquire(self, session_id: str) -> None: ...

    def release(self, session_id: str) -> None: ...

    def get_or_create_session(self, session_id: str, cookies: Dict=None) -> "SessionWrapper": ...

    def configure_rate_limit(
        self,
        session_id: str,
        requests_per_second: Optional[float],
    ) -> None: ...

class InterceptorsHooks(Protocol):
    session: SessionHooks
