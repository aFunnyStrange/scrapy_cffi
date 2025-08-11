from functools import cached_property
from curl_cffi.requests import Response as CffiResponse
from ..selector import Selector
from ....utils import ProtobufFactory
from typing import Tuple, Dict, List, Union

class Response(object):
    def __init__(self,
        session_id="",
        raw_response: CffiResponse=None,
        meta={},
        dont_filter=None,
        callback=None,
        errback=None,
        desc_text="",
        request=None,
        **kwargs
    ) -> None:
        self.session_id = session_id
        self.raw_response = raw_response
        self.meta = meta
        self.dont_filter = dont_filter
        self.callback = callback
        self.errback = errback
        self.desc_text = desc_text
        self.request = request
        self.kwargs = kwargs

class HttpResponse(Response):
    def __init__(self, 
        session_id="",
        raw_response: CffiResponse=None,
        meta={},
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
        if "json" in ctype:
            return "json"
        if "html" in ctype:
            return "html"
        return None

    @cached_property
    def selector(self):
        stype = self.get_selector_type()
        if not stype:
            return None
        return Selector(response=self.raw_response, type=stype)

    def xpath(self, query):
        return self.selector.xpath(query)
    
    def css(self, query):
        return self.selector.css(query)

    def re(self, pattern):
        return self.selector.re(pattern)
    
    def json(self):
        return self.raw_response.json()
    
    def extract_json(self, key: str="", re_rule: str=""):
        return self.selector.extract_json(key, re_rule=re_rule)

    def extract_json_strong(self, key: str="", strict_level=2, re_rule=""):
        return self.selector.extract_json_strong(key, strict_level=strict_level, re_rule=re_rule)
    
    def protobuf_decode(self) -> Tuple[Dict, Dict]:
        return ProtobufFactory.protobuf_decode(self.content)
    
    def grpc_decode(self) -> Union[Tuple[Dict, Dict], List[Tuple[Dict, Dict]]]:
        return ProtobufFactory.grpc_decode(self.content)
    
class WebSocketResponse(Response):
    def __init__(self, 
        session_id="",
        websocket_id="",
        msg=b'',
        meta={},
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