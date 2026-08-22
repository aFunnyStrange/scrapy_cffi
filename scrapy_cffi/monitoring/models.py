"""Define stable wire models for experimental crawler monitoring."""

from typing import Dict, List, Optional

from pydantic import Field

from ..models import StrictValidatedModel


class MonitorEvent(StrictValidatedModel):
    """Describe one crawler lifecycle or aggregated counter update."""

    worker_id: str = Field(min_length=1, max_length=200)
    event: str = Field(min_length=1, max_length=80)
    timestamp: float = Field(ge=0)
    spider_name: Optional[str] = Field(default=None, max_length=200)
    counters: Dict[str, int] = Field(default_factory=dict)
    detail: Optional[str] = Field(default=None, max_length=1000)


class WorkerSnapshot(StrictValidatedModel):
    """Represent the latest in-memory state known by one monitoring Hub."""

    worker_id: str
    status: str
    last_event: str
    last_seen: float
    spiders: List[str] = Field(default_factory=list)
    counters: Dict[str, int] = Field(default_factory=dict)
    detail: Optional[str] = None


__all__ = ["MonitorEvent", "WorkerSnapshot"]
