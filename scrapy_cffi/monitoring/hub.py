"""Build an optional FastAPI crawler-monitoring application."""

import asyncio
from html import escape
from typing import Dict, List, Optional

from .models import MonitorEvent, WorkerSnapshot


class MonitorStore:
    """Own process-local crawler snapshots for the experimental Hub."""

    def __init__(self) -> None:
        """Initialize empty state without starting a server or task."""
        self._workers: Dict[str, WorkerSnapshot] = {}
        self._active_engines: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def record(self, event: MonitorEvent) -> WorkerSnapshot:
        """Merge one event into the corresponding worker snapshot."""
        async with self._lock:
            previous = self._workers.get(event.worker_id)
            spiders = list(previous.spiders) if previous else []
            if event.spider_name and event.spider_name not in spiders:
                spiders.append(event.spider_name)
            status = previous.status if previous else "registered"
            active_engines = self._active_engines.get(event.worker_id, 0)
            if event.event == "engine_started":
                active_engines += 1
                self._active_engines[event.worker_id] = active_engines
                status = "running"
            elif event.event == "engine_stopped":
                active_engines = max(0, active_engines - 1)
                self._active_engines[event.worker_id] = active_engines
                status = "running" if active_engines else "stopped"
            elif event.event == "spider_opened":
                status = "running"
            elif event.event in ("task_error", "spider_error"):
                status = "error"
            snapshot = WorkerSnapshot(
                worker_id=event.worker_id,
                status=status,
                last_event=event.event,
                last_seen=event.timestamp,
                spiders=sorted(spiders),
                counters=dict(event.counters),
                detail=event.detail,
            )
            self._workers[event.worker_id] = snapshot
            return snapshot

    async def list_workers(self) -> List[WorkerSnapshot]:
        """Return snapshots ordered by most recent observation first."""
        async with self._lock:
            return sorted(
                self._workers.values(),
                key=lambda worker: worker.last_seen,
                reverse=True,
            )


def _dashboard_html() -> str:
    """Return a dependency-free dashboard that polls the JSON API."""
    title = escape("scrapy-cffi crawler monitor")
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title><style>
body{font-family:system-ui,sans-serif;margin:2rem;background:#111827;color:#e5e7eb}h1{font-size:1.4rem}
.note{color:#9ca3af}table{width:100%%;border-collapse:collapse;margin-top:1rem;background:#1f2937}
th,td{text-align:left;padding:.7rem;border-bottom:1px solid #374151}th{color:#93c5fd}.running{color:#34d399}.error{color:#f87171}
</style></head><body><h1>%s</h1><p class="note">Experimental, in-memory crawler observation only. No task scheduling or durable history.</p>
<table><thead><tr><th>Worker</th><th>Status</th><th>Spiders</th><th>Last event</th><th>Last seen</th><th>Counters</th></tr></thead><tbody id="workers"></tbody></table>
<script>function esc(v){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}async function refresh(){const r=await fetch('/api/v1/workers');const rows=await r.json();document.getElementById('workers').innerHTML=rows.map(w=>`<tr><td>${esc(w.worker_id)}</td><td class="${esc(w.status)}">${esc(w.status)}</td><td>${esc(w.spiders.join(', '))}</td><td>${esc(w.last_event)}</td><td>${esc(new Date(w.last_seen*1000).toLocaleString())}</td><td><code>${esc(JSON.stringify(w.counters))}</code></td></tr>`).join('')}refresh();setInterval(refresh,2000);</script>
</body></html>""" % (title, title)


def create_monitor_app(store: Optional[MonitorStore] = None):
    """Create the FastAPI app or raise an actionable optional-extra error."""
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
    app = FastAPI(title="scrapy-cffi crawler monitor", version="experimental")
    app.state.monitor_store = monitor_store

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

    @app.post("/api/v1/workers/events", response_model=WorkerSnapshot)
    async def record_event(event: MonitorEvent) -> WorkerSnapshot:
        """Register or update one crawler worker observation."""
        return await monitor_store.record(event)

    return app


__all__ = ["MonitorStore", "create_monitor_app"]
