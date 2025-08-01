from typing import Protocol, Dict, Any

class SessionHooks(Protocol):
    def register_sessions(self, sessions: Dict[str, Any]) -> None: ...

class SpidersHooks(Protocol):
    session: SessionHooks
