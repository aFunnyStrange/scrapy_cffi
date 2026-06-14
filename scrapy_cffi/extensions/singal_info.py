from pydantic.dataclasses import dataclass
from typing import Any, Dict, Optional, Union

# Keep this module free of core/spider imports — SignalInfo is loaded while
# extensions.__init__ is still initializing (e.g. settings validating EXTENSIONS_PATH).


@dataclass(config={"extra": "ignore", "arbitrary_types_allowed": True})
class SignalInfo:
    signal_time: Optional[float] = 0.0
    reason: Optional[str] = ""
    next: Optional[str] = ""
    response: Optional[Any] = None
    exception: Optional[BaseException] = None
    spider: Optional[Any] = None
    request: Optional[Any] = None
    item: Optional[Union[Any, Dict]] = None

__all__ = [
    "SignalInfo"
]