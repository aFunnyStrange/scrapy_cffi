import asyncio, json
from ..core.downloader.internet import Request, HttpRequest, WebSocketRequest
from .fingerprint import build_fingerprint_bytes, fingerprint_sha1
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..spiders import Spider
    from ..settings import SettingsInfo
    from ..cpy.cpy_resources.bloom.fallback import BloomFilterPy

class BaseFingerprint:
    def __init__(self, settings: "SettingsInfo"=None, **kwargs):
        self.settings = settings
        self.include_headers = self.settings.INCLUDE_HEADERS
        self.kwargs = kwargs

    def create_bytes(self, request: Request) -> bytes:
        if not isinstance(self.include_headers, list):
            raise ValueError("INCLUDE_HEADERS in settings is not list.")
        body_parts: list[bytes] = []
        method = None
        if isinstance(request, HttpRequest):
            method = request.method
            if isinstance(request.data, bytes):
                body_parts.append(request.data)
            elif isinstance(request.data, dict):
                body_parts.append(
                    json.dumps(request.data, separators=(",", ":"), sort_keys=True).encode("latin-1")
                )
        elif isinstance(request, WebSocketRequest):
            for msg in request.send_message:
                body_parts.append(msg.data)
        return build_fingerprint_bytes(
            request,
            include_headers=self.include_headers,
            method=method,
            body_parts=body_parts or None,
        )

    def get_fingerprint(self, request: Request) -> str:
        return fingerprint_sha1(self.create_bytes(request))
    
class MemoryDupeFilter(BaseFingerprint):
    def __init__(self, settings: "SettingsInfo"=None, **kwargs):
        super().__init__(settings=settings, **kwargs)
        self.new_seen: set[str] = set() # Requests marked as seen but not yet sent
        self.sent_seen: set[str] = set() # Requests that have been seen and already sent
        self.lock = asyncio.Lock()
        
    async def request_seen(self, request: "Request"=None, **kwargs):
        fingerprint = self.get_fingerprint(request=request)
        is_seen = fingerprint in self.new_seen
        # If the request fingerprint is already in new_seen (i.e., seen before), return True.
        # Otherwise, add the fingerprint to new_seen and check if it is present in sent_seen,
        # which indicates the request has already been dispatched.
        if is_seen:
            return is_seen
        self.new_seen.add(fingerprint)
        return fingerprint in self.sent_seen
    
    async def mark_sent(self, request: "Request", spider: "Spider", **kwargs):
        if not request.dont_filter:
            async with self.lock:
                self.sent_seen.add(self.get_fingerprint(request=request))
    
class BloomDupeFilter(BaseFingerprint):
    def __init__(self, settings: "SettingsInfo"=None, **kwargs):
        super().__init__(settings=settings, **kwargs)
        import bloom
        self.new_seen: "BloomFilterPy" = bloom.BloomFilter(size=self.settings.BLOOM_INFO.SIZE, expected=self.settings.BLOOM_INFO.EXPECTED, hash_count=self.settings.BLOOM_INFO.HASH_COUNT)
        self.sent_seen: "BloomFilterPy" = bloom.BloomFilter(size=self.settings.BLOOM_INFO.SIZE, expected=self.settings.BLOOM_INFO.EXPECTED, hash_count=self.settings.BLOOM_INFO.HASH_COUNT)
        self.lock = asyncio.Lock()

    async def request_seen(self, request: "Request"=None, **kwargs):
        origin_fp_bytes = self.create_bytes(request=request)
        is_seen = self.new_seen.exists(origin_fp_bytes)
        # If the request fingerprint is already in new_seen (i.e., seen before), return True.
        # Otherwise, add the fingerprint to new_seen and check if it is present in sent_seen,
        # which indicates the request has already been dispatched.
        if is_seen:
            return is_seen
        self.new_seen.add(origin_fp_bytes)
        return self.sent_seen.exists(origin_fp_bytes)

    async def mark_sent(self, request: "Request", spider: "Spider", **kwargs):
        if not request.dont_filter:
            async with self.lock:
                self.sent_seen.add(self.create_bytes(request=request))