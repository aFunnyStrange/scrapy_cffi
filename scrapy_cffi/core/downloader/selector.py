from typing import Dict, Tuple
from parsel import Selector as ParselSelector
from typing import TYPE_CHECKING, Union, Dict, List
from functools import cached_property
from ...utils import extract_nested_objects, JSONScanner, ProtobufFactory
if TYPE_CHECKING:
    from .internet import HttpResponse

class Selector:
    def __init__(self, response: "HttpResponse"=None, type: str=None, **kwargs):
        if not response:
            raise ValueError("[Selector] Missing response")
        self.response = response
        self._text = getattr(response, "text", None)
        self._type = type or "html"

    @cached_property
    def _parsel_selector(self):
        if isinstance(self._text, str) and self._type in ("html", "xml"):
            return ParselSelector(text=self._text, type=self._type)
        return None
    
    def xpath(self, query):
        if self._parsel_selector:
            return self._parsel_selector.xpath(query)
        return []

    def css(self, query):
        if self._parsel_selector:
            return self._parsel_selector.css(query)
        return []

    def re(self, pattern):
        if self._parsel_selector:
            return self._parsel_selector.re(pattern)
        return []

    def json(self):
        return getattr(self.response, "json", lambda: None)()

    def extract_json(self, key: str="", re_rule: str="") -> Union[List[Union[Dict, str]], Dict, str]:
        if isinstance(self._text, str):
            return extract_nested_objects(text=self._text, key=key, re_rule=re_rule)
        return []

    def extract_json_strong(self, key=None, strict_level=2, re_rule="") -> Union[List[Union[Dict, str]], Dict, str]:
        if isinstance(self._text, str):
            return JSONScanner(strict_level=strict_level).scan_text(text=self._text, key=key, re_rule=re_rule)
        return []

    def protobuf_decode(self) -> Tuple[Dict, Dict]:
        content = getattr(self.response, "content", None)
        if content and isinstance(content, (bytes, bytearray)):
            return ProtobufFactory.protobuf_decode(self.response.content)
        return {}, {}
    
    def grpc_decode(self) -> Union[Tuple[Dict, Dict], List[Tuple[Dict, Dict]]]:
        content = getattr(self.response, "content", None)
        if content and isinstance(content, (bytes, bytearray)):
            return ProtobufFactory.grpc_decode(self.response.content)
        return {}, {}