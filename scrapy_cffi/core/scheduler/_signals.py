"""Lazy scheduler signal helpers — avoid importing extensions at module load."""

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...extensions import SignalManager


def emit_request_scheduled(signal_manager: "SignalManager", request: Any) -> None:
    from ...extensions import SignalInfo, signals

    signal_manager.send(
        signal=signals.request_scheduled,
        data=SignalInfo(signal_time=time.time(), request=request),
    )


def emit_request_dropped(signal_manager: "SignalManager", request: Any, reason: str) -> None:
    from ...extensions import SignalInfo, signals

    signal_manager.send(
        signal=signals.request_dropped,
        data=SignalInfo(signal_time=time.time(), request=request, reason=reason),
    )
