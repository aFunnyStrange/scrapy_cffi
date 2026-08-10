import base64
from typing import Optional, Dict, Any
from pydantic import Field, field_validator
from .base import StrictValidatedModel
from ..platform import WebSocketFlag
from ..utils.protobuf import ProtobufFactory

class WebSocketMsg(StrictValidatedModel):
    data: Any = Field(default=b"")
    flags: Optional[WebSocketFlag] = Field(default=WebSocketFlag.BINARY)

    @field_validator("data", mode="before")
    @classmethod
    def ensure_bytes_and_infer_flag(cls, v, info):
        if isinstance(v, str):
            if not info.data.get("flags"):
                info.data["flags"] = WebSocketFlag.TEXT
            return v.encode("utf-8")
        elif isinstance(v, bytes):
            return v
        elif v is None:
            return b""
        raise TypeError(f"Unsupported data type for WebSocketMsg.data: {type(v)}")

    def to_dict(self) -> dict:
        return {
            "__wsmsg__": True,
            "data": base64.b64encode(self.data).decode(),
            "flags": int(self.flags or WebSocketFlag.BINARY),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WebSocketMsg":
        data = base64.b64decode(d["data"])
        flags = WebSocketFlag(d.get("flags", int(WebSocketFlag.BINARY)))
        return cls(data=data, flags=flags)

    def as_send_args(self) -> tuple[bytes, WebSocketFlag]:
        return self.data, self.flags or WebSocketFlag.BINARY

    def __repr__(self) -> str:
        f_name = getattr(self.flags, "name", str(self.flags))
        return f"<WebSocketMsg flags={f_name} len={len(self.data)}>"

    def protobuf_encode(self, typedef: Optional[Dict] = None):
        if typedef is None:
            return self
        self.data = ProtobufFactory.protobuf_encode(data=self.data, typedef=typedef)
        self.flags = WebSocketFlag.BINARY
        return self

    def grpc_encode(self, typedef: Optional[Dict] = None, is_gzip: bool = False):
        if typedef is None:
            return self
        self.data = ProtobufFactory.grpc_encode(data=self.data, typedef=typedef, is_gzip=is_gzip)
        self.flags = WebSocketFlag.BINARY
        return self
