import base64
from typing import Optional, Dict, Any
from curl_cffi.const import CurlWsFlag
from pydantic import Field, field_validator
from .base import StrictValidatedModel
from ..utils import ProtobufFactory

class WebSocketMsg(StrictValidatedModel):
    data: Any = Field(default=b"")
    flags: Optional[CurlWsFlag] = Field(default=CurlWsFlag.BINARY)

    @field_validator("data", mode="before")
    @classmethod
    def ensure_bytes_and_infer_flag(cls, v, info):
        if isinstance(v, str):
            if not info.data.get("flags"):
                info.data["flags"] = CurlWsFlag.TEXT
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
            "flags": int(self.flags or CurlWsFlag.BINARY),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WebSocketMsg":
        data = base64.b64decode(d["data"])
        flags = CurlWsFlag(d.get("flags", int(CurlWsFlag.BINARY)))
        return cls(data=data, flags=flags)

    def as_send_args(self) -> tuple[bytes, CurlWsFlag]:
        return self.data, self.flags or CurlWsFlag.BINARY

    def __repr__(self) -> str:
        f_name = getattr(self.flags, "name", str(self.flags))
        return f"<WebSocketMsg flags={f_name} len={len(self.data)}>"

    def protobuf_encode(self, typedef: Optional[Dict] = None):
        if typedef is None:
            return self
        self.data = ProtobufFactory.protobuf_encode(data=self.data, typedef=typedef)
        self.flags = CurlWsFlag.BINARY
        return self

    def grpc_encode(self, typedef: Optional[Dict] = None, is_gzip: bool = False):
        if typedef is None:
            return self
        self.data = ProtobufFactory.grpc_encode(data=self.data, typedef=typedef, is_gzip=is_gzip)
        self.flags = CurlWsFlag.BINARY
        return self
