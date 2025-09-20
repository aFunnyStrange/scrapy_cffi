import asyncio, hashlib, json
from ..core.downloader.internet import Request, HttpRequest, WebSocketRequest
from typing import TYPE_CHECKING, Set
if TYPE_CHECKING:
    from ..spiders import Spider
    from ..models.api import SettingsInfo

class DupeFilter(object):
    def __init__(self, settings: "SettingsInfo"=None, **kwargs):
        self.new_seen: set[str] = set() # Requests marked as seen but not yet sent
        self.sent_seen: set[str] = set() # Requests that have been seen and already sent
        self.lock = asyncio.Lock()

        self.settings = settings
        self.include_headers = self.settings.INCLUDE_HEADERS
        self.kwargs = kwargs

    def get_fingerprint(self, request: "Request") -> str:
        fp = hashlib.sha1()
        if not isinstance(self.include_headers, list):
            raise ValueError("INCLUDE_HEADERS in settings is not list.")
        include_headers = {}
        for header_key in self.include_headers:
            has_header_key =  request.find_header_key(key=header_key)
            if has_header_key:
                include_headers[has_header_key.lower()] = request.headers[has_header_key]
        fp.update(f'{request.url}|{json.dumps(include_headers, separators=(",", ":"), sort_keys=True)}'.encode('latin-1'))
        if isinstance(request, HttpRequest):
            fp.update(f'{request.method}|'.encode('latin-1'))
            if isinstance(request.data, bytes):
                fp.update(request.data)
            elif isinstance(request.data, dict):
                fp.update(json.dumps(request.data, separators=(",", ":"), sort_keys=True).encode('latin-1'))
        elif isinstance(request, WebSocketRequest):
            for msg in request.send_message:
                fp.update(msg)
        return fp.hexdigest()

    def request_seen(self, new_seen: Set=None, request: "Request"=None, **kwargs):
        if not new_seen:
            new_seen = self.new_seen

        fingerprint = self.get_fingerprint(request=request)
        is_seen = fingerprint in new_seen
        # If the request fingerprint is already in new_seen (i.e., seen before), return True.
        # Otherwise, add the fingerprint to new_seen and check if it is present in sent_seen,
        # which indicates the request has already been dispatched.
        if is_seen:
            return is_seen
        new_seen.add(fingerprint)
        return fingerprint in self.sent_seen

    async def mark_sent(self, request: "Request", spider: "Spider", **kwargs):
        if not request.dont_filter:
            async with self.lock:
                self.sent_seen.add(self.get_fingerprint(request=request))