from pydantic.dataclasses import dataclass
from typing import TYPE_CHECKING, Union, Dict, Optional
if TYPE_CHECKING:
    from ..core import HttpRequest, WebSocketRequest, HttpResponse, WebSocketResponse
    from ..spiders import BaseSpider
    from ..item import Item

@dataclass(config={"extra": "ignore"})
class SingalInfo:
    signal_time: Optional[float] = 0.0
    reason: Optional[str] = ""
    next: Optional[str] = ""
    response: Optional[Union["HttpResponse", "WebSocketResponse"]] = None
    exception: Optional[BaseException | None] = None
    spider: Optional["BaseSpider"] = None
    request: Optional[Union["HttpRequest", "WebSocketRequest"]] = None
    item: Optional[Union["Item", Dict]] = None

__all__ = [
    "SingalInfo"
]