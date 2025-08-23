from pydantic.dataclasses import dataclass
from ..core.downloader.internet import HttpRequest, WebSocketRequest, HttpResponse, WebSocketResponse
from ..spiders.base import BaseSpider
from ..item.base import Item
from typing import Union, Dict, Optional

@dataclass(config={"extra": "ignore", "arbitrary_types_allowed": True})
class SingalInfo:
    signal_time: Optional[float] = 0.0
    reason: Optional[str] = ""
    next: Optional[str] = ""
    response: Optional[Union[HttpResponse, WebSocketResponse]] = None
    exception: Optional[BaseException] = None
    spider: Optional[BaseSpider] = None
    request: Optional[Union[HttpRequest, WebSocketRequest]] = None
    item: Optional[Union[Item, Dict]] = None

__all__ = [
    "SingalInfo"
]