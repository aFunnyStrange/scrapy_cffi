from typing import TYPE_CHECKING, cast
if TYPE_CHECKING:
    from ..crawler import Crawler
    from .spiders import SpidersHooks
    from .pipelines import PipelinesHooks, _PipelinesHooks
    from .interceptors import InterceptorsHooks
    from .signals import SignalsHooks

class Hooks:
    def __init__(self, **funcs):
        for name, func in funcs.items():
            setattr(self, name, func)

def spiders_hooks(crawler: "Crawler") -> "SpidersHooks":
    hooks_obj = Hooks(
        session=Hooks(
            register_sessions=crawler.sessions.register_sessions_batch,
        )
    )
    return cast(Hooks, hooks_obj)

def _pipelines_hooks(crawler: "Crawler") -> "_PipelinesHooks":
    hooks_obj = Hooks(
        session=Hooks(
            mark_end=crawler.sessions.mark_end,
            session_end_cookies=crawler.sessions.session_end_cookies,
        ),
    )
    return cast(Hooks, hooks_obj)

def pipelines_hooks(crawler: "Crawler") -> "PipelinesHooks":
    hooks_obj = Hooks(
        signals=Hooks(
            send=crawler.signalManager.send
        )
    )
    return cast(Hooks, hooks_obj)

def interceptors_hooks(crawler: "Crawler") -> "InterceptorsHooks":
    hooks_obj = Hooks(
        session=Hooks(
            acquire=crawler.sessions.acquire,
            release=crawler.sessions.release,
            get_or_create_session=crawler.sessions.get_or_create_session,
        )
    )
    return cast(Hooks, hooks_obj)

def signals_hooks(crawler: "Crawler") -> "SignalsHooks":
    hooks_obj = Hooks(
        signals=Hooks(
            connect=crawler.signalManager.connect
        )
    )
    return cast(Hooks, hooks_obj)

__all__ = [
    "spiders_hooks",
    "_pipelines_hooks",
    "pipelines_hooks",
    "interceptors_hooks",
    "signals_hooks",
]