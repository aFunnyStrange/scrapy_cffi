from functools import cached_property
from ..selector import Selector
from ....utils import ProtobufFactory
from ....platform.http import AsyncHttpStreamProtocol, HttpResponseProtocol
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Tuple, Dict, List, Optional, Union


@dataclass(frozen=True)
class SSEEvent:
    """Represent one parsed Server-Sent Event."""

    data: str
    event: str = "message"
    id: Optional[str] = None
    retry: Optional[int] = None

class Response(object):
    def __init__(self,
        session_id="",
        raw_response: HttpResponseProtocol=None,
        meta=None,
        dont_filter=None,
        callback=None,
        errback=None,
        desc_text="",
        request=None,
        **kwargs
    ) -> None:
        self.session_id = session_id
        self.raw_response = raw_response
        self.meta = meta or {}
        self.dont_filter = dont_filter
        self.callback = callback
        self.errback = errback
        self.desc_text = desc_text
        self.request = request
        self.kwargs = kwargs

class HttpResponse(Response):
    def __init__(self, 
        session_id="",
        raw_response: HttpResponseProtocol=None,
        meta=None,
        dont_filter=None,
        callback=None,
        errback=None,
        desc_text="",
        request=None,
        **kwargs
    ):
        super().__init__(
            session_id=session_id,
            raw_response=raw_response,
            meta=meta,
            dont_filter=dont_filter,
            callback=callback,
            errback=errback,
            desc_text=desc_text,
            request=request,
            **kwargs
        )
        self.status_code = self.raw_response.status_code     
        self.content = self.raw_response.content
        self.text = self.raw_response.text

    def get_selector_type(self):
        ctype = self.raw_response.headers.get("Content-Type", "").lower()
        if "xml" in ctype:
            return "xml"
        elif "html" in ctype:
            return "html"
        return "other"

    @cached_property
    def selector(self):
        return Selector(response=self.raw_response, type=self.get_selector_type())

    def xpath(self, query):
        return self.selector.xpath(query)
    
    def css(self, query):
        return self.selector.css(query)

    def re(self, pattern):
        return self.selector.re(pattern)
    
    def json(self):
        return self.selector.json()
    
    def extract_json(self, key: str="", re_rule: str="") -> Union[List[Union[Dict, str]], Dict, str]:
        return self.selector.extract_json(key, re_rule=re_rule)

    def extract_json_strong(self, key: str="", strict_level=2, re_rule="") -> Union[List[Union[Dict, str]], Dict, str]:
        return self.selector.extract_json_strong(key, strict_level=strict_level, re_rule=re_rule)

    def extract_json_chain(self, keys: List[str], strict_level=2, re_rule="") -> Union[List[Union[Dict, str]], Dict, str]:
        return self.selector.extract_json_chain(keys=keys, strict_level=strict_level, re_rule=re_rule)
    
    def protobuf_decode(self) -> Tuple[Dict, Dict]:
        return self.selector.protobuf_decode()
    
    def grpc_decode(self) -> Union[Tuple[Dict, Dict], List[Tuple[Dict, Dict]]]:
        return self.selector.grpc_decode()


class StreamResponse(Response):
    """Expose a live HTTP response stream with bytes, lines, and SSE iteration."""

    def __init__(
        self,
        stream: AsyncHttpStreamProtocol,
        release: Optional[Callable[[], None]] = None,
        **kwargs
    ) -> None:
        """Take ownership of a platform stream until ``aclose`` is called."""
        super().__init__(raw_response=stream, **kwargs)
        self._stream = stream
        self._release = release
        self._closed = False
        self.status_code = stream.status_code
        self.headers = stream.headers

    async def aiter_bytes(self, chunk_size: Optional[int] = None) -> AsyncIterator[bytes]:
        """Yield raw response body chunks without full buffering."""
        async for chunk in self._stream.aiter_bytes(chunk_size=chunk_size):
            yield chunk

    async def aiter_lines(self) -> AsyncIterator[str]:
        """Yield decoded response lines."""
        async for line in self._stream.aiter_lines():
            yield line

    async def aiter_sse(self, max_event_size: int = 1048576) -> AsyncIterator[SSEEvent]:
        """Parse a bounded ``text/event-stream`` body into SSE events."""
        data_lines: List[str] = []
        event_name = "message"
        event_id = None
        retry = None
        event_size = 0

        async for line in self.aiter_lines():
            line = line.rstrip("\r")
            if line == "":
                if data_lines:
                    yield SSEEvent(
                        data="\n".join(data_lines),
                        event=event_name,
                        id=event_id,
                        retry=retry,
                    )
                data_lines = []
                event_name = "message"
                retry = None
                event_size = 0
                continue
            if line.startswith(":"):
                continue

            field, separator, value = line.partition(":")
            if separator and value.startswith(" "):
                value = value[1:]
            event_size += len(value.encode("utf-8"))
            if event_size > max_event_size:
                raise ValueError("SSE event exceeded max_event_size")
            if field == "data":
                data_lines.append(value)
            elif field == "event":
                event_name = value or "message"
            elif field == "id" and "\x00" not in value:
                event_id = value
            elif field == "retry" and value.isdigit():
                retry = int(value)

        if data_lines:
            yield SSEEvent(
                data="\n".join(data_lines),
                event=event_name,
                id=event_id,
                retry=retry,
            )

    async def aclose(self) -> None:
        """Close the platform stream and release downloader capacity once."""
        if self._closed:
            return
        self._closed = True
        try:
            await self._stream.close()
        finally:
            if self._release is not None:
                release = self._release
                self._release = None
                release()
    
class WebSocketResponse(Response):
    def __init__(self, 
        session_id="",
        websocket_id="",
        msg=b'',
        meta=None,
        callback=None,
        errback=None,
        desc_text="",
        request=None,
        **kwargs
    ):
        super().__init__(session_id=session_id, meta=meta, callback=callback, errback=errback, desc_text=desc_text, request=request, **kwargs)
        self.websocket_id = websocket_id
        self.msg = msg

    def protobuf_decode(self) -> Tuple[Dict, Dict]:
        return ProtobufFactory.protobuf_decode(self.msg)
    
    def grpc_decode(self) -> Union[Tuple[Dict, Dict], List[Tuple[Dict, Dict]]]:
        return ProtobufFactory.grpc_decode(self.msg)
