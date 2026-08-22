"""Construct narrow capability objects passed to user components."""

from typing import TYPE_CHECKING, cast


async def _noop_scheduler_async(*args, **kwargs):
    """Used when a scheduler hook is missing on a scheduler implementation."""
    return None


def _noop_scheduler_sync(*args, **kwargs):
    """Ignore one missing optional synchronous scheduler capability."""
    return None


if TYPE_CHECKING:
    from ..crawler import Crawler
    from .spiders import SpidersHooks
    from .pipelines import PipelinesHooks, _PipelinesHooks
    from .interceptors import InterceptorsHooks
    from .signals import SignalsHooks

class Hooks:
    """Hold a deliberately small dynamic capability surface."""

    def __init__(self, **funcs):
        """Attach explicitly selected capabilities by name."""
        for name, func in funcs.items():
            setattr(self, name, func)

def spiders_hooks(crawler: "Crawler", scheduler) -> "SpidersHooks":
    """Expose session and scheduler capabilities to one Spider."""
    hooks_obj = Hooks(
        session=Hooks(
            register_sessions=crawler.sessions.register_sessions_batch,
            get_session_cookies=crawler.sessions.get_session_cookies,
            configure_rate_limit=crawler.sessions.configure_rate_limit,
        ),
        scheduler=Hooks(
            get_start_req=getattr(scheduler, "get_start_req", _noop_scheduler_async),
            ack_start_req=getattr(scheduler, "ack_start_req", _noop_scheduler_async),
            attach_start_req=getattr(scheduler, "attach_start_req", _noop_scheduler_sync),
        )
    )
    return cast(Hooks, hooks_obj)

def _pipelines_hooks(crawler: "Crawler") -> "_PipelinesHooks":
    """Expose internal pipeline session capabilities."""
    hooks_obj = Hooks(
        session=Hooks(
            mark_end=crawler.sessions.mark_end,
            get_session_cookies=crawler.sessions.get_session_cookies,
            configure_rate_limit=crawler.sessions.configure_rate_limit,
        ),
    )
    return cast(Hooks, hooks_obj)

def pipelines_hooks(crawler: "Crawler") -> "PipelinesHooks":
    """Expose public pipeline session and signal capabilities."""
    hooks_obj = Hooks(
        session=Hooks(
            get_session_cookies=crawler.sessions.get_session_cookies,
            configure_rate_limit=crawler.sessions.configure_rate_limit,
        ),
        signals=Hooks(
            send=crawler.signalManager.send
        )
    )
    return cast(Hooks, hooks_obj)

def interceptors_hooks(crawler: "Crawler") -> "InterceptorsHooks":
    """Expose session leasing capabilities to interceptors."""
    hooks_obj = Hooks(
        session=Hooks(
            acquire=crawler.sessions.acquire,
            release=crawler.sessions.release,
            get_or_create_session=crawler.sessions.get_or_create_session,
            configure_rate_limit=crawler.sessions.configure_rate_limit,
        )
    )
    return cast(Hooks, hooks_obj)

def signals_hooks(crawler: "Crawler") -> "SignalsHooks":
    """Expose observation context and subscriptions to extensions."""
    hooks_obj = Hooks(
        settings=crawler.settings,
        logger=crawler.logger,
        run_context=crawler.run_context,
        stop_event=crawler.stop_event,
        session=Hooks(
            configure_rate_limit=crawler.sessions.configure_rate_limit,
        ),
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
