"""Maintain bounded process-local worker and run observations for the Hub."""

import asyncio
import time
from typing import Dict, List, Optional, Tuple

from ..runtime.state import RunState, WorkerAvailability, WorkerState
from .models import MonitorEvent, RunSnapshot, WorkerSnapshot


WorkerKey = Tuple[str, str]


class MonitorStore:
    """Own replaceable process-local snapshots, not durable business state."""

    def __init__(
        self,
        stale_after: float = 45.0,
        max_workers: int = 1000,
        max_runs: int = 10000,
    ) -> None:
        """Configure when missing observations mean availability is unknown."""
        if stale_after <= 0:
            raise ValueError("stale_after must be positive")
        if max_workers <= 0 or max_runs <= 0:
            raise ValueError("observation retention limits must be positive")
        self.stale_after = stale_after
        self.max_workers = max_workers
        self.max_runs = max_runs
        self._workers: Dict[WorkerKey, WorkerSnapshot] = {}
        self._runs: Dict[str, RunSnapshot] = {}
        self._active_engines: Dict[WorkerKey, int] = {}
        self._run_active_engines: Dict[str, int] = {}
        self._run_event_ids: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def record(self, event: MonitorEvent) -> WorkerSnapshot:
        """Merge one event while rejecting duplicate or stale run sequences."""
        async with self._lock:
            if event.run_id and not self._accept_run_event(event):
                worker_key = (event.worker_id, event.instance_id)
                return self._workers[worker_key]
            self._release_terminal_engines(event)
            worker = self._record_worker(event)
            if event.run_id:
                self._record_run(event)
                worker = worker.model_copy(
                    update={"active_runs": self._count_active_runs(worker_key=(event.worker_id, event.instance_id))}
                )
                self._workers[(event.worker_id, event.instance_id)] = worker
            self._enforce_limits()
            return worker

    def _release_terminal_engines(self, event: MonitorEvent) -> None:
        """Forget orphaned Engine counts after an explicit run terminal event."""
        if event.run_id is None or event.run_state not in (
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.CANCELLED,
            RunState.KILLED,
        ):
            return
        remaining = self._run_active_engines.get(event.run_id, 0)
        if not remaining:
            return
        key = (event.worker_id, event.instance_id)
        self._active_engines[key] = max(
            0,
            self._active_engines.get(key, 0) - remaining,
        )
        self._run_active_engines[event.run_id] = 0

    def _accept_run_event(self, event: MonitorEvent) -> bool:
        """Return whether a run event is new enough to change snapshots."""
        run_id = event.run_id
        if run_id is None:
            return True
        if self._run_event_ids.get(run_id) == event.event_id:
            return False
        previous = self._runs.get(run_id)
        if previous is not None and event.sequence > 0 and event.sequence <= previous.sequence:
            return False
        self._run_event_ids[run_id] = event.event_id
        return True

    def _record_worker(self, event: MonitorEvent) -> WorkerSnapshot:
        """Update explicit worker lifecycle without promoting item errors."""
        key = (event.worker_id, event.instance_id)
        previous = self._workers.get(key)
        spiders = self._merge_spiders(previous.spiders if previous else [], event.spider_name)
        status = previous.status if previous else WorkerState.REGISTERED
        active_engines = self._active_engines.get(key, 0)
        if event.event == "engine_started":
            active_engines += 1
        elif event.event == "engine_stopped":
            active_engines = max(0, active_engines - 1)
        self._active_engines[key] = active_engines
        if event.worker_state is not None:
            status = event.worker_state
        elif event.event in ("engine_started", "spider_opened"):
            status = WorkerState.RUNNING
        elif event.event == "engine_stopped":
            status = WorkerState.RUNNING if active_engines else WorkerState.STOPPED
        observed_at = time.time()
        snapshot = WorkerSnapshot(
            worker_id=event.worker_id,
            instance_id=event.instance_id,
            worker_type=event.worker_type,
            status=status,
            availability=WorkerAvailability.ONLINE,
            last_event=event.event,
            last_seen=event.timestamp,
            observed_at=observed_at,
            active_runs=previous.active_runs if previous else 0,
            spiders=spiders,
            counters=dict(event.counters),
            detail=event.detail,
        )
        self._workers[key] = snapshot
        return snapshot

    def _record_run(self, event: MonitorEvent) -> None:
        """Update one execution snapshot independently from worker health."""
        run_id = event.run_id
        if run_id is None:
            return
        previous = self._runs.get(run_id)
        spiders = self._merge_spiders(previous.spiders if previous else [], event.spider_name)
        active_engines = self._run_active_engines.get(run_id, 0)
        state = previous.state if previous else RunState.ACCEPTED
        if event.event == "engine_started":
            active_engines += 1
        elif event.event == "engine_stopped":
            active_engines = max(0, active_engines - 1)
        self._run_active_engines[run_id] = active_engines
        if event.run_state is not None:
            state = event.run_state
        elif event.event in ("engine_started", "spider_opened"):
            state = RunState.RUNNING
        elif event.event == "engine_stopped" and not active_engines:
            state = RunState.COMPLETED
        self._runs[run_id] = RunSnapshot(
            run_id=run_id,
            worker_id=event.worker_id,
            instance_id=event.instance_id,
            task_id=event.task_id,
            worker_type=event.worker_type,
            state=state,
            last_event=event.event,
            last_seen=event.timestamp,
            observed_at=time.time(),
            sequence=max(event.sequence, previous.sequence if previous else 0),
            spiders=spiders,
            counters=dict(event.counters),
            detail=event.detail,
        )

    def _count_active_runs(self, worker_key: WorkerKey) -> int:
        """Count nonterminal runs belonging to one worker instance."""
        terminal = {
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.CANCELLED,
            RunState.KILLED,
        }
        return sum(
            1
            for run in self._runs.values()
            if (run.worker_id, run.instance_id) == worker_key and run.state not in terminal
        )

    def _enforce_limits(self) -> None:
        """Evict oldest snapshots so the default in-memory Store stays bounded."""
        while len(self._runs) > self.max_runs:
            terminal = {
                RunState.COMPLETED,
                RunState.FAILED,
                RunState.CANCELLED,
                RunState.KILLED,
            }
            run_id = min(
                self._runs,
                key=lambda key: (
                    self._runs[key].state not in terminal,
                    self._runs[key].observed_at,
                ),
            )
            self._runs.pop(run_id, None)
            self._run_active_engines.pop(run_id, None)
            self._run_event_ids.pop(run_id, None)
        while len(self._workers) > self.max_workers:
            worker_key = min(
                self._workers,
                key=lambda key: (
                    self._workers[key].status != WorkerState.STOPPED,
                    self._workers[key].observed_at,
                ),
            )
            self._workers.pop(worker_key, None)
            self._active_engines.pop(worker_key, None)

    @staticmethod
    def _merge_spiders(spiders: List[str], spider_name: Optional[str]) -> List[str]:
        """Return a deterministic spider-name union."""
        merged = list(spiders)
        if spider_name and spider_name not in merged:
            merged.append(spider_name)
        return sorted(merged)

    async def list_workers(self) -> List[WorkerSnapshot]:
        """Return observations with derived availability, never inferred completion."""
        now = time.time()
        async with self._lock:
            workers = []
            for worker in self._workers.values():
                availability = WorkerAvailability.ONLINE
                if (
                    worker.status in (
                        WorkerState.REGISTERED,
                        WorkerState.STARTING,
                        WorkerState.RUNNING,
                        WorkerState.DRAINING,
                    )
                    and now - worker.observed_at > self.stale_after
                ):
                    availability = WorkerAvailability.UNREACHABLE
                workers.append(worker.model_copy(update={"availability": availability}))
            return sorted(
                workers,
                key=lambda worker: worker.observed_at,
                reverse=True,
            )

    async def list_runs(self) -> List[RunSnapshot]:
        """Return execution observations ordered by the latest runtime fact."""
        async with self._lock:
            return sorted(
                self._runs.values(),
                key=lambda run: run.observed_at,
                reverse=True,
            )


__all__ = ["MonitorStore"]
