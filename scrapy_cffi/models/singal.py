from dataclasses import dataclass
from typing import TYPE_CHECKING, Union
if TYPE_CHECKING:
    from ..core import HttpRequest, WebSocketRequest, HttpResponse, WebSocketResponse
    from ..spiders import BaseSpider
    from ..item import Item

@dataclass
class SingalInfo:
    signal_time: float = 0.0
    reason: str = ""
    next: str = ""
    response: Union["HttpResponse", "WebSocketResponse"] = None
    exception: BaseException = None
    spider: "BaseSpider" = None
    request: Union["HttpRequest", "WebSocketRequest"] = None
    item: "Item" = None

__all__ = [
    "SingalInfo"
]