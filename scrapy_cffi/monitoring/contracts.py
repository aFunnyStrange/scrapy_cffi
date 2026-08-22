"""Define replaceable observation and durable-task query capabilities."""

from typing import List, Optional, Protocol

from .models import MonitorEvent, RunSnapshot, TaskSnapshot, WorkerSnapshot


class ObservationStore(Protocol):
    """Store runtime observations without becoming business task storage."""

    async def record(self, event: MonitorEvent) -> WorkerSnapshot:
        """Merge one immutable runtime event into observation snapshots."""
        ...

    async def list_workers(self) -> List[WorkerSnapshot]:
        """List currently known worker-instance observations."""
        ...

    async def list_runs(self) -> List[RunSnapshot]:
        """List currently known execution observations."""
        ...


class TaskStateProvider(Protocol):
    """Read application-owned durable task facts for optional Hub display."""

    async def list_tasks(self) -> List[TaskSnapshot]:
        """Return a bounded application-defined task view."""
        ...

    async def get_task(self, task_id: str) -> Optional[TaskSnapshot]:
        """Return one durable task view when it exists."""
        ...


__all__ = ["ObservationStore", "TaskStateProvider"]
