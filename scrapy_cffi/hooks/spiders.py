from typing import Protocol, Dict, Any

class SessionHooks(Protocol):
    def register_sessions(self, sessions: Dict[str, Any]) -> None: ...

    def get_session_cookies(self, session_id: str) -> Dict: ...

class SpidersHooks(Protocol):
    session: SessionHooks
