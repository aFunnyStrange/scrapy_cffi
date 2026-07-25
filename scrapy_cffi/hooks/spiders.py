from typing import Protocol, Dict, Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..spiders import Spider

class SessionHooks(Protocol):
    def register_sessions(self, sessions: Dict[str, Any]) -> str: ...

    def get_session_cookies(self, session_id: str) -> Dict: ...

class SchedulerHooks(Protocol):
    async def get_start_req(self, spider: "Spider", **kwargs) -> Any: ...

    async def ack_start_req(self, spider: "Spider", message, **kwargs) -> Any: ...

    def attach_start_req(self, request, message) -> None: ...

class SpidersHooks(Protocol):
    session: SessionHooks
    scheduler: SchedulerHooks
