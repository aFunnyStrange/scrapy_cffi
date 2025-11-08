import json as jsonlib
import gzip, base64, warnings
from curl_cffi.const import CurlWsFlag
from urllib.parse import urlencode
from typing import Optional, Union, Dict, Tuple, List
from ....models.api import WebSocketMsg
from ....utils import ProtobufFactory
from .registry import register_request_class, get_request_class

class Request(object):
    ENCODE_FIELDS = set()

    def __init__(self,
        session_id="",
        url="",
        params=None,
        headers=None,
        cookies=None,
        proxies=None,
        timeout=30,
        allow_redirects=True,
        max_redirects=30,
        verify=None,
        impersonate=None,
        ja3=None,
        akamai=None,
        meta=None,
        dont_filter=None,
        callback=None,
        errback=None,
        desc_text="",
        no_proxy=False,
        **kwargs
    ) -> None:
        meta = meta or {}

        self.session_id = session_id
        self.url = self.join_url_params(url, params=params)
        self.headers = headers
        self.cookies = cookies
        self.proxies = proxies
        self.timeout=timeout
        self.allow_redirects=allow_redirects
        self.max_redirects=max_redirects
        self.verify=verify
        self.impersonate=impersonate
        self.ja3=ja3
        self.akamai=akamai
        self.meta = meta
        self.dont_filter = dont_filter
        self.callback = callback if isinstance(callback, str) else (callback.__name__ if callback else None)
        self.errback = errback if isinstance(errback, str) else (errback.__name__ if errback else None)
        self.desc_text = desc_text
        self.no_proxy = no_proxy
        self.kwargs = kwargs

    def is_protobuf(self):
        has_key = self.find_header_key(key="content-type")
        if not has_key:
            return False
        return any([it in self.headers[has_key].lower() for it in ["protobuf", "grpc"]])
    
    def find_header_key(self, key: str) -> Optional[str]:
        if self.headers:
            key_lower = key.lower()
            for k in self.headers:
                if k.lower() == key_lower:
                    return k
            return None

    def set_header(self, headers: Optional[Dict], key: str, value: str, mode: str = "append", sep: str = ", ") -> Dict:
        if headers is None:
            headers = {}
        real_key = self.find_header_key(key)
        if real_key is None:
            headers[key] = value
        else:
            if mode == "overwrite":
                headers[real_key] = value
            elif mode == "append":
                existing_value = headers[real_key]
                if value.lower() not in existing_value.lower():
                    headers[real_key] = f"{existing_value}{sep}{value}"
        return headers

    def join_url_params(self, url="", params=None):
        return f'{url}?{urlencode(params, doseq=True)}' if params else url
    
    def to_dict(self) -> Dict:
        def _encode_data(data):
            if isinstance(data, bytes):
                return {"__bytes__": True, "b64": base64.b64encode(data).decode()}
            elif isinstance(data, WebSocketMsg):
                return data.to_dict()
            elif isinstance(data, list):
                return [_encode_data(v) for v in data]
            elif isinstance(data, dict):
                return {k: _encode_data(v) for k, v in data.items()}
            elif isinstance(data, tuple):
                return tuple(_encode_data(v) for v in data)
            else:
                return data

        result = {}
        for key, value in self.__dict__.items():
            if key in self.ENCODE_FIELDS:
                result[key] = _encode_data(value)
            else:
                result[key] = value
        return result
    
    def to_bytes(self) -> bytes:
        d = self.to_dict()
        d["class"] = self.__class__.__name__
        json_bytes = jsonlib.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return gzip.compress(json_bytes)

    @classmethod
    def from_bytes(cls, b: bytes) -> "Request":
        d = jsonlib.loads(gzip.decompress(b).decode("utf-8"))
        cls_name = d.pop("class", None)
        actual_cls: Union[HttpRequest, WebSocketRequest] = get_request_class(cls_name)
        return actual_cls._from_dict(d)
    
    @staticmethod
    def _decode_data(data):
        if isinstance(data, dict):
            if data.get("__bytes__"):
                return base64.b64decode(data["b64"])
            if data.get("__wsmsg__"):
                return WebSocketMsg.from_dict(data)
            return {k: Request._decode_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [Request._decode_data(v) for v in data]
        elif isinstance(data, tuple):
            return tuple(Request._decode_data(v) for v in data)
        else:
            return data

    @classmethod
    def _from_dict(cls, d):
        kwargs = cls._decode_data(d.pop("kwargs", {}))
        for key in cls.ENCODE_FIELDS:
            if key in d:
                d[key] = cls._decode_data(d[key])
        return cls(**d, **kwargs)
    
@register_request_class
class HttpRequest(Request):
    ENCODE_FIELDS = {
        "headers", "data", "cookies", "proxies", "meta", "kwargs"
    }

    def __init__(self, 
        session_id="",
        url="", 
        params=None, 
        method="GET", 
        headers=None, 
        data=None, 
        json=None, 
        cookies=None, 
        proxies=None, 
        timeout=30,
        allow_redirects=True,
        max_redirects=30,
        verify=None,
        impersonate=None,
        ja3=None,
        akamai=None,
        meta=None, 
        dont_filter=None, 
        callback=None, 
        errback=None,
        desc_text="",
        no_proxy=False,
        **kwargs
    ):
        self.method = method.upper()
        if json:
            data = jsonlib.dumps(json, separators=(",", ":"))
            headers = self.set_header(headers=headers, key="Content-Type", value="application/json", mode="append", sep="; ")

        self.data = data
        super().__init__(
            session_id=session_id,
            url=url, 
            params=params, 
            headers=headers, 
            cookies=cookies, 
            proxies=proxies, 
            timeout=timeout,
            allow_redirects=allow_redirects,
            max_redirects=max_redirects,
            verify=verify,
            impersonate=impersonate,
            ja3=ja3,
            akamai=akamai,
            meta=meta, 
            dont_filter=dont_filter, 
            callback=callback, 
            errback=errback,
            desc_text=desc_text,
            no_proxy=no_proxy,
            **kwargs
        )
        if self.is_protobuf() and not isinstance(data, bytes):
            warnings.warn(f'[WARNING] Content-Type includes "protobuf", but the provided data is not in bytes format.')

    def protobuf_encode(self, typedef: Dict):
        self.data = ProtobufFactory.protobuf_encode(data=self.data, typedef=typedef)
        return self
    
    def grpc_encode(self, typedef_or_stream: Union[Dict, List[Tuple[Dict, Dict]]], is_gzip: bool=False):
        if isinstance(typedef_or_stream, dict):
            self.data = ProtobufFactory.grpc_encode(data=self.data, typedef=typedef_or_stream, is_gzip=is_gzip)
        elif isinstance(typedef_or_stream, list):
            self.data = ProtobufFactory.grpc_stream_encode(data=typedef_or_stream, is_gzip=is_gzip)
        return self
    
@register_request_class
class MediaRequest(HttpRequest):
    def __init__(self, 
        session_id="",
        url="", 
        params=None, 
        method="GET", 
        headers=None, 
        data=None, 
        json=None, 
        cookies=None, 
        proxies=None, 
        single_part_size=2999999, # The byte size of a segment
        media_size=0,
        timeout=30,
        allow_redirects=True,
        max_redirects=30,
        verify=None,
        impersonate=None,
        ja3=None,
        akamai=None,
        meta=None, 
        dont_filter=None, 
        callback=None, 
        errback=None,
        desc_text="",
        no_proxy=False,
        **kwargs
    ):
        super().__init__(
            session_id=session_id,
            url=url, 
            params=params, 
            method=method,
            headers=headers, 
            data=data,
            json=json,
            cookies=cookies, 
            proxies=proxies, 
            timeout=timeout,
            allow_redirects=allow_redirects,
            max_redirects=max_redirects,
            verify=verify,
            impersonate=impersonate,
            ja3=ja3,
            akamai=akamai,
            meta=meta, 
            dont_filter=dont_filter, 
            callback=callback, 
            errback=errback,
            desc_text=desc_text,
            no_proxy=no_proxy,
            **kwargs
        )
        self.single_part_size = single_part_size
        self.media_size = media_size
    
@register_request_class
class WebSocketRequest(Request):
    ENCODE_FIELDS = {
        "headers", "send_message", "ping_data", "cookies", "proxies", "meta", "kwargs"
    }

    def __init__(
        self,
        session_id="",
        websocket_id="",
        url="",
        params=None,
        headers=None,
        send_message: Union[WebSocketMsg, List[WebSocketMsg]] = None,
        ping_data: WebSocketMsg=None,
        ping_interval: float=15.0,
        cookies=None,
        proxies=None,
        timeout=30,
        allow_redirects=True,
        max_redirects=30,
        verify=None,
        impersonate=None,
        ja3=None,
        akamai=None,
        meta=None,
        dont_filter=None,
        callback=None,
        errback=None,
        desc_text="",
        no_proxy=False,
        **kwargs,
    ):
        super().__init__(
            session_id=session_id,
            url=url,
            params=params,
            headers=headers,
            cookies=cookies,
            proxies=proxies,
            timeout=timeout,
            allow_redirects=allow_redirects,
            max_redirects=max_redirects,
            verify=verify,
            impersonate=impersonate,
            ja3=ja3,
            akamai=akamai,
            meta=meta,
            dont_filter=dont_filter,
            callback=callback,
            errback=errback,
            desc_text=desc_text,
            no_proxy=no_proxy,
            **kwargs,
        )
        self.websocket_id = websocket_id
        if send_message is None:
            send_message = [WebSocketMsg(data=b"ping", flags=CurlWsFlag.BINARY)]
        elif not isinstance(send_message, list):
            send_message = [send_message]

        if not all([isinstance(it, WebSocketMsg) for it in send_message]):
            warning_text = f"send_message must be WebSocketMsg in versions >=0.2.2, got {type(send_message)}"
            warnings.warn(warning_text)
            raise ValueError(warning_text)
        
        if ping_data and not isinstance(ping_data, WebSocketMsg):
            raise ValueError(f"ping_data must be WebSocketMsg, got {type(ping_data)}")

        self.send_message = send_message

        self.ping_data = ping_data
        self.ping_interval = ping_interval

    def grpc_stream_encode(self) -> "WebSocketRequest":
        if not self.send_message:
            raise ValueError("No WebSocket messages to encode.")

        # all_flags = {m.flags for m in self.send_message}
        # if len(all_flags) > 1:
        #     raise ValueError(f"Cannot stream-encode messages with different flags: {all_flags}")

        for m in self.send_message:
            if not isinstance(m.data, (bytes, bytearray)):
                raise TypeError(f"Message {m!r} not encoded as bytes.")

        stream_bytes = b"".join(m.data for m in self.send_message)
        self.send_message = [WebSocketMsg(data=stream_bytes, flags=CurlWsFlag.BINARY)]
        return self