from typing import Protocol, Dict, Any, TYPE_CHECKING, Union
if TYPE_CHECKING:
    from ..spiders import Spider

class SessionHooks(Protocol):
    def register_sessions(self, sessions: Dict[str, Any]) -> None: ...

    def get_session_cookies(self, session_id: str) -> Dict: ...

class SchedulerHooks(Protocol):
    def get_start_req(self, spider: "Spider", **kwargs) -> Union[None, bytes]: ...

class SpidersHooks(Protocol):
    session: SessionHooks
    scheduler: SchedulerHooks
