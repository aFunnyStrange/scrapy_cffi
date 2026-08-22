"""Define scheduler-neutral worker run identity and observation contracts."""

import os
import socket
import time
from enum import Enum
from typing import Dict, Optional, Protocol
from uuid import uuid4

from pydantic import Field

from ..models import StrictValidatedModel


_PROCESS_INSTANCE_ID = str(uuid4())


class WorkerState(str, Enum):
    """Describe the explicit lifecycle reported by one worker instance."""

    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    DRAINING = "draining"
    STOPPED = "stopped"


class WorkerAvailability(str, Enum):
    """Describe whether the Hub has recent observations from a worker."""

    ONLINE = "online"
    UNREACHABLE = "unreachable"


class RunState(str, Enum):
    """Describe one framework execution without imposing business semantics."""

    ACCEPTED = "accepted"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    KILLED = "killed"


class EventCategory(str, Enum):
    """Classify observations independently from worker lifecycle state."""

    LIFECYCLE = "lifecycle"
    HEARTBEAT = "heartbeat"
    COUNTERS = "counters"
    ERROR = "error"


class RunContext(StrictValidatedModel):
    """Carry correlation identity supplied by an optional outer scheduler."""

    worker_id: Optional[str] = Field(default=None, min_length=1, max_length=200)
    instance_id: str = Field(
        default_factory=lambda: "%s:%s" % (_PROCESS_INSTANCE_ID, os.getpid()),
        min_length=1,
        max_length=200,
    )
    run_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=200)
    task_id: Optional[str] = Field(default=None, min_length=1, max_length=200)
    attempt: int = Field(default=1, ge=1)
    trace_id: Optional[str] = Field(default=None, min_length=1, max_length=200)
    labels: Dict[str, str] = Field(default_factory=dict)

    @classmethod
    def create(cls, **kwargs: object) -> "RunContext":
        """Create a context using stable process identity and a fresh run ID."""
        return cls.model_validate(kwargs)

    def resolved_worker_id(self) -> str:
        """Return the configured identity or a safe local process fallback."""
        return self.worker_id or "%s:%s" % (socket.gethostname(), os.getpid())


class RunEvent(StrictValidatedModel):
    """Describe one immutable runtime fact emitted to observation sinks."""

    schema_version: int = Field(default=1, ge=1)
    event_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=200)
    sequence: int = Field(default=0, ge=0)
    worker_id: str = Field(min_length=1, max_length=200)
    instance_id: str = Field(default="legacy", min_length=1, max_length=200)
    run_id: Optional[str] = Field(default=None, min_length=1, max_length=200)
    task_id: Optional[str] = Field(default=None, min_length=1, max_length=200)
    worker_type: str = Field(default="crawler", min_length=1, max_length=80)
    event: str = Field(min_length=1, max_length=80)
    category: EventCategory = EventCategory.LIFECYCLE
    timestamp: float = Field(default_factory=time.time, ge=0)
    worker_state: Optional[WorkerState] = None
    run_state: Optional[RunState] = None
    spider_name: Optional[str] = Field(default=None, max_length=200)
    counters: Dict[str, int] = Field(default_factory=dict)
    detail: Optional[str] = Field(default=None, max_length=1000)


class RunOutcome(StrictValidatedModel):
    """Return one execution result for an outer scheduler to interpret."""

    context: RunContext
    state: RunState
    started_at: float = Field(ge=0)
    finished_at: float = Field(ge=0)
    counters: Dict[str, int] = Field(default_factory=dict)
    error_type: Optional[str] = Field(default=None, max_length=200)
    error_summary: Optional[str] = Field(default=None, max_length=1000)


class RunEventSink(Protocol):
    """Publish runtime observations without owning durable business state."""

    async def publish(self, event: RunEvent) -> None:
        """Publish one immutable execution fact."""
        ...


__all__ = [
    "EventCategory",
    "RunContext",
    "RunEvent",
    "RunEventSink",
    "RunOutcome",
    "RunState",
    "WorkerAvailability",
    "WorkerState",
]
