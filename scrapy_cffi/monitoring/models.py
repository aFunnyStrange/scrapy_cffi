"""Define stable wire models for worker, run, and task observations."""

from typing import Dict, List, Optional

from pydantic import Field

from ..models import StrictValidatedModel
from ..runtime.state import (
    RunEvent,
    RunState,
    WorkerAvailability,
    WorkerState,
)


class MonitorEvent(RunEvent):
    """Retain the monitoring-specific public name for a generic run event."""


class WorkerSnapshot(StrictValidatedModel):
    """Represent the latest lifecycle and availability known for one instance."""

    worker_id: str
    instance_id: str = "legacy"
    worker_type: str = "crawler"
    status: WorkerState
    availability: WorkerAvailability = WorkerAvailability.ONLINE
    last_event: str
    last_seen: float
    observed_at: float
    active_runs: int = Field(default=0, ge=0)
    spiders: List[str] = Field(default_factory=list)
    counters: Dict[str, int] = Field(default_factory=dict)
    detail: Optional[str] = None


class RunSnapshot(StrictValidatedModel):
    """Represent one framework execution without claiming business truth."""

    run_id: str
    worker_id: str
    instance_id: str
    task_id: Optional[str] = None
    worker_type: str = "crawler"
    state: RunState
    last_event: str
    last_seen: float
    observed_at: float
    sequence: int = Field(default=0, ge=0)
    spiders: List[str] = Field(default_factory=list)
    counters: Dict[str, int] = Field(default_factory=dict)
    detail: Optional[str] = None


class TaskSnapshot(StrictValidatedModel):
    """Expose application-owned durable task facts through a read-only adapter."""

    task_id: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=80)
    updated_at: float = Field(ge=0)
    run_id: Optional[str] = Field(default=None, max_length=200)
    detail: Optional[str] = Field(default=None, max_length=1000)
    metadata: Dict[str, str] = Field(default_factory=dict)


__all__ = [
    "MonitorEvent",
    "RunSnapshot",
    "TaskSnapshot",
    "WorkerSnapshot",
]
