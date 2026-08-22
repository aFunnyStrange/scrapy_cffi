"""Publish crawler observations to an optional monitoring Hub."""

import asyncio
import json
from urllib import request

from .models import MonitorEvent


class MonitorClient:
    """Send bounded JSON events through the standard-library HTTP client."""

    def __init__(self, hub_url: str, timeout: float = 3.0) -> None:
        """Store a normalized Hub endpoint and request timeout."""
        self.events_url = "%s/api/v1/workers/events" % hub_url.rstrip("/")
        self.timeout = timeout

    def _publish_sync(self, event: MonitorEvent) -> None:
        """Perform one blocking HTTP request for the thread adapter."""
        payload = json.dumps(event.model_dump(mode="json")).encode("utf-8")
        http_request = request.Request(
            self.events_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(http_request, timeout=self.timeout) as response:
            response.read()

    async def publish(self, event: MonitorEvent) -> None:
        """Publish without blocking the crawler's asyncio event loop."""
        await asyncio.to_thread(self._publish_sync, event)


__all__ = ["MonitorClient"]
