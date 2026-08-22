"""Build an optional FastAPI worker-observation application."""

from html import escape
from typing import Dict, List, Optional

from .contracts import ObservationStore, TaskStateProvider
from .models import (
    MonitorEvent,
    RunSnapshot,
    TaskSnapshot,
    WorkerSnapshot,
)
from .store import MonitorStore


def _dashboard_html() -> str:
    """Return a dependency-free dashboard that polls the JSON API."""
    title = escape("scrapy-cffi worker monitor")
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title><style>
body{font-family:system-ui,sans-serif;margin:2rem;background:#111827;color:#e5e7eb}h1{font-size:1.4rem}
.note{color:#9ca3af}table{width:100%%;border-collapse:collapse;margin-top:1rem;background:#1f2937}
th,td{text-align:left;padding:.7rem;border-bottom:1px solid #374151}th{color:#93c5fd}.running{color:#34d399}.error{color:#f87171}
</style></head><body><h1>%s</h1><p class="note">Experimental observation only. Durable business task state remains application-owned.</p>
<h2>Worker instances</h2>
<table><thead><tr><th>Worker</th><th>Instance</th><th>Status</th><th>Availability</th><th>Runs</th><th>Spiders</th><th>Last event</th><th>Last seen</th><th>Counters</th></tr></thead><tbody id="workers"></tbody></table>
<h2>Framework runs</h2>
<table><thead><tr><th>Run</th><th>Task</th><th>Worker</th><th>State</th><th>Spiders</th><th>Last event</th><th>Counters</th></tr></thead><tbody id="runs"></tbody></table>
<h2>Application tasks</h2><p class="note">Read-only and visible only when a TaskStateProvider is registered.</p>
<table><thead><tr><th>Task</th><th>State</th><th>Run</th><th>Updated</th><th>Detail</th></tr></thead><tbody id="tasks"></tbody></table>
<script>function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}async function json(path){const r=await fetch(path);return r.json()}async function refresh(){const [workers,runs,tasks]=await Promise.all([json('/api/v1/workers'),json('/api/v1/runs'),json('/api/v1/tasks')]);document.getElementById('workers').innerHTML=workers.map(w=>`<tr><td>${esc(w.worker_id)}</td><td>${esc(w.instance_id)}</td><td class="${esc(w.status)}">${esc(w.status)}</td><td>${esc(w.availability)}</td><td>${esc(w.active_runs)}</td><td>${esc(w.spiders.join(', '))}</td><td>${esc(w.last_event)}</td><td>${esc(new Date(w.last_seen*1000).toLocaleString())}</td><td><code>${esc(JSON.stringify(w.counters))}</code></td></tr>`).join('');document.getElementById('runs').innerHTML=runs.map(r=>`<tr><td>${esc(r.run_id)}</td><td>${esc(r.task_id)}</td><td>${esc(r.worker_id)}</td><td>${esc(r.state)}</td><td>${esc(r.spiders.join(', '))}</td><td>${esc(r.last_event)}</td><td><code>${esc(JSON.stringify(r.counters))}</code></td></tr>`).join('');document.getElementById('tasks').innerHTML=tasks.map(t=>`<tr><td>${esc(t.task_id)}</td><td>${esc(t.state)}</td><td>${esc(t.run_id)}</td><td>${esc(new Date(t.updated_at*1000).toLocaleString())}</td><td>${esc(t.detail)}</td></tr>`).join('')}refresh();setInterval(refresh,2000);</script>
</body></html>""" % (title, title)


def create_monitor_app(
    store: Optional[ObservationStore] = None,
    task_state_provider: Optional[TaskStateProvider] = None,
):
    """Create the Hub with replaceable observation and read-only task sources."""
    try:
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
    except ImportError as exc:
        raise RuntimeError(
            "Crawler monitoring requires optional dependencies. "
            "Install with: pip install 'scrapy_cffi[server]' "
            "(fastapi>=0.115, uvicorn>=0.30)"
        ) from exc

    monitor_store = store or MonitorStore()
    app = FastAPI(title="scrapy-cffi worker monitor", version="experimental")
    app.state.monitor_store = monitor_store
    app.state.task_state_provider = task_state_provider

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        """Render the small polling-based crawler dashboard."""
        return _dashboard_html()

    @app.get("/health")
    async def health() -> Dict[str, str]:
        """Report whether the monitoring process can serve requests."""
        return {"status": "ok"}

    @app.get("/api/v1/workers", response_model=List[WorkerSnapshot])
    async def list_workers() -> List[WorkerSnapshot]:
        """Return all currently known in-memory crawler workers."""
        return await monitor_store.list_workers()

    @app.get("/api/v1/runs", response_model=List[RunSnapshot])
    async def list_runs() -> List[RunSnapshot]:
        """Return framework-run observations without business-state claims."""
        return await monitor_store.list_runs()

    @app.get("/api/v1/tasks", response_model=List[TaskSnapshot])
    async def list_tasks() -> List[TaskSnapshot]:
        """Return application-owned task facts when a provider is registered."""
        if task_state_provider is None:
            return []
        return await task_state_provider.list_tasks()

    @app.get("/api/v1/tasks/{task_id}", response_model=Optional[TaskSnapshot])
    async def get_task(task_id: str) -> Optional[TaskSnapshot]:
        """Return one application-owned task fact through the read-only seam."""
        if task_state_provider is None:
            return None
        return await task_state_provider.get_task(task_id)

    @app.post("/api/v1/workers/events", response_model=WorkerSnapshot)
    async def record_event(event: MonitorEvent) -> WorkerSnapshot:
        """Register or update one crawler worker observation."""
        return await monitor_store.record(event)

    return app


__all__ = ["MonitorStore", "create_monitor_app"]
