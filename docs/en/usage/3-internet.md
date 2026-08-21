# 1.Introduction
`scrapy_cffi` uses `curl_cffi` through a framework-owned asynchronous platform
adapter. Crawler code depends on stable HTTP, streaming, and WebSocket
Protocols instead of importing `curl_cffi.requests.AsyncSession` directly.

Qualified dependency ranges:

- Python 3.9: `curl_cffi>=0.7.4,<0.14`
- Python 3.10+: `curl_cffi>=0.7.4,<0.16`

This keeps Python 3.9 support while allowing curl_cffi 0.14/0.15 on runtimes
supported by those releases. The adapter normalizes their WebSocket lifecycle
and sync/async method differences. A future request implementation can satisfy
the same `scrapy_cffi.platform.AsyncHttpSessionProtocol` without changing the
crawler engine.

**Key features of** `curl_cffi`:
- Supports both synchronous and asynchronous requests.
- Handles `HTTP`, `HTTPS`, `WebSocket (WS/WSS)` protocols.
- Allows detailed TLS fingerprint customization, enabling strong `TLS/JA3` fingerprint emulation.


---


# 2.Request Objects
The `scrapy_cffi` framework provides two built-in request types: `HttpRequest` and `WebSocketRequest`.
## 2.1 Request
A shared superclass for `HttpRequest` and `WebSocketRequest`, used as the unified request interface within the framework.

The request API closely mirrors `curl_cffi`, supporting parameters such as:

```python
url: str
params: Optional[Dict] = None
headers: Optional[HeaderTypes] = None
cookies: Optional[CookieTypes] = None
proxies: Optional[ProxySpec] = None
timeout: Union[int] = 30
max_retry_times: Optional[int] = None
retry_delay: Optional[float] = None
allow_redirects: bool = True
max_redirects: int = 30
verify: Optional[bool] = None
impersonate: Optional[BrowserTypeLiteral] = None
ja3: Optional[str] = None
akamai: Optional[str] = None
```

In `scrapy_cffi 0.4.2`, self-built curl profiles use the existing
request-scoped `impersonate` argument. Configure only the native implementation
directory globally; do not configure a global impersonation profile:

```python
from pathlib import Path

from scrapy_cffi.internet import HttpRequest
from scrapy_cffi.settings import SettingsInfo


settings = SettingsInfo(
    CURL_CFFI_RUNTIME_DIR=Path("D:/native/my-curl-build"),
)

request = HttpRequest(
    url="https://tls.peet.ws/api/all",
    impersonate="my-browser-stable",
)
```

The framework does not bundle or name any concrete custom profile. Put an
optional `scrapy_cffi_profiles.toml` beside the native files to register
user-owned aliases when the directory is activated:

```toml
schema_version = 1

[profiles.my-browser-stable]
impersonate = "my_native_profile_v1"

[profiles.my-browser-stable.client_hints]
Sec-CH-UA-Full-Version-List = '"Chromium";v="123.0.0.0"'
Sec-CH-UA-Arch = '"x86"'
```

The same registration can be performed programmatically with
`register_profile("my-browser-stable", "my_native_profile_v1")`. Registered
aliases are selected through `impersonate`. Unknown values pass through
unchanged, preserving curl_cffi built-in profiles and direct native targets,
so a manifest is optional. Omitting `impersonate` selects no profile.

The built-in Client Hints download interceptor is always registered. It is
transport-version independent (HTTP/1.1 and HTTP/2 are both supported), but is
dormant unless an HTTPS request explicitly selects `impersonate`. When a
response advertises `Accept-CH`, requested high-entropy values are read from
that profile's manifest metadata and sent on later requests for the same
origin, session, and profile. `Clear-Site-Data: "clientHints"` clears the
origin state. Existing user headers win.

For values that must be resolved at runtime, override the optional spider
callback:

```python
async def resolve_client_hint(self, name, origin, response):
    if name.lower() == "sec-ch-ua-platform-version":
        return '"15.0.0"'
    return None
```

The interceptor never creates or retries a request. In particular, it does
not automatically replay `Critical-CH`; this preserves the framework's
acquire/release ownership for finite crawls. A value learned from the response
applies to subsequent requests only. Session state is included in persistent
scheduler snapshots.

`params` are merged into `url` at construction time (`url?key=value&...`). For deduplication, query parameters are canonicalized (sorted by key/value) when building the fingerprint, so parameter order does not affect duplicate detection.

Additional Framework-specific Parameters:
| Attribute | Description |
| --------- | ----------- |
| **session_id** | Unique session identifier. If empty, uses the framework's default session. Can be released using `{"session_end": True, "session_id": ...}` in your item. |
| **meta** | Dictionary for storing user-defined metadata, accessible in callbacks. |
| **dont_filter** | Skip duplicate filtering for this request. The individual request setting takes precedence over the global `DONT_FILTER` setting in `settings.py`. If absent, the global setting applies. |
| **callback** | Callback function to handle the response. |
| **errback** | Error handler if the request fails. |
| **desc_text** | Human-readable string for identifying the request in logs or callbacks. |
| **no_proxy** | Disables proxy for this specific request, even if global proxy settings are active. |
| **stream** | Keep the response body open for incremental consumption through `StreamResponse`. |
| **max_retry_times** | Override `MAX_REQ_TIMES` for this request. The value is the total number of attempts. |
| **retry_delay** | Override `DELAY_REQ_TIME` for this request; zero is allowed. |

### Timeout errbacks

HTTP, streaming, and WebSocket transport timeouts become
`RequestTimeoutError` after retries are exhausted. The failure reaches the
request's `errback` and exposes `request`, `exception`, `timeout`, and
`attempts`:

```python
from scrapy_cffi.exceptions import RequestTimeoutError

yield HttpRequest(
    url=url,
    timeout=10,
    max_retry_times=3,
    retry_delay=0.5,
    callback=self.parse,
    errback=self.on_error,
)

async def on_error(self, failure):
    if isinstance(failure, RequestTimeoutError):
        self.logger.warning(
            "task=%s timeout attempts=%s",
            failure.request.meta.get("task_id"),
            failure.attempts,
        )
```

Advanced options via `**kwargs` (passed directly to `curl_cffi`, no autocomplete):

```python
files: Optional[Dict] = None,
auth: Optional[Tuple[str, str]] = None,
proxy: Optional[str] = None,
proxy_auth: Optional[Tuple[str, str]] = None,
referer: Optional[str] = None,
accept_encoding: Optional[str] = "gzip, deflate, br",
content_callback: Optional[Callable] = None,
extra_fp: Optional[Union[ExtraFingerprints, ExtraFpDict]] = None,
default_headers: Optional[bool] = None,
default_encoding: Union[str, Callable[[bytes], str]] = "utf-8",
quote: Union[str, Literal[False]] = "",
http_version: Optional[Union[HttpVersion, str]] = None,
interface: Optional[str] = None,
cert: Optional[Union[str, Tuple[str, str]]] = None,
max_recv_speed: int = 0,
multipart: Optional[CurlMime] = None,
```

**Note**: Any unsupported keyword arguments will raise an error.

### HTTP/3 / QUIC (experimental request support)

HTTP/3 is a per-request transport preference, not a WebSocket-style listener:

```python
from scrapy_cffi.internet import HttpRequest
from scrapy_cffi.platform import HttpVersion

yield HttpRequest(
    url="https://example.com/",
    http_version=HttpVersion.HTTP_3_ONLY,
    callback=self.parse,
)
```

`HTTP_3` permits curl's earlier-version fallback; `HTTP_3_ONLY` fails when the
active curl build, UDP path, server, or proxy cannot establish QUIC. The
generated Demo contains a minimal `aioquic` HTTP/3 server and request example.
Server Push, QUIC unidirectional-stream callbacks, datagrams, WebTransport, and
MASQUE proxy control are not exposed by the framework yet. No background QUIC
listener Task is created. Traditional HTTP proxies generally cannot tunnel
UDP; proxy-preserved HTTP/3 requires explicit CONNECT-UDP/MASQUE support in the
proxy and curl build.

## 2.2 HttpRequest
### 2.2.1 Attributes
| Attribute | Description |
| --------- | ----------- |
| **method** | HTTP method (`GET`, `POST`, `PUT`, etc.) – case-insensitive |
| **data** | Request body: `Dict`, `List`, `str`, `BytesIO`, or `bytes` |
| **json** | JSON body: `Dict[str, Union[str, int]]` only (bytes not supported) |
| **stream** | When true, the callback receives `StreamResponse` instead of a buffered `HttpResponse`. |

### 2.2.2 Streaming and SSE

Streaming requests keep one bounded downloader slot until the callback finishes
or the response is explicitly closed. Cancellation and crawler shutdown close
the underlying connection automatically.

```python
from scrapy_cffi.internet import HttpRequest, StreamResponse


async def start(self):
    yield HttpRequest(
        url="https://example.com/v1/chat/completions",
        method="POST",
        json={"stream": True},
        stream=True,
        callback=self.parse_stream,
    )


async def parse_stream(self, response: StreamResponse):
    async for event in response.aiter_sse():
        if event.data == "[DONE]":
            break
        yield {"event": event.event, "data": event.data}
```

Available stream APIs:

- `aiter_bytes(chunk_size=None)` for binary chunks;
- `aiter_lines()` for UTF-8 decoded lines;
- `aiter_sse(max_event_size=1048576)` for bounded Server-Sent Events;
- `aclose()` for early explicit release. It is idempotent.

`SSEEvent` exposes `data`, `event`, `id`, and `retry`. Multiple `data:` lines
are joined with a newline. The default one-event limit prevents an unterminated
or malicious event from growing memory without a bound.

### 2.2.3 Methods
#### 2.2.3.1 protobuf_encode(self, typedef: Dict)
Encodes the request body (`data`) into a binary Protobuf payload using the given type definition. The method modifies the request in-place and returns the updated `HttpRequest` object for chaining.

**Parameters**: 
    **typedef**: **Dict** - Protobuf type definition using the `blackboxprotobuf` format.

**Returns**: The updated `HttpRequest` object with its `data` field replaced by the Protobuf-encoded binary payload.

**Example:**
```python
yield HttpRequest(
    data={...},
).protobuf_encode({...})
```

#### 2.2.3.2 grpc_encode(self, typedef_or_stream: Union[Dict, List[Tuple[Dict, Dict]]], is_gzip: bool=False)
Encodes the request body (`data`) into a valid gRPC framed message and returns the updated request object for chaining.

**Parameters**: 
    **typedef_or_stream**: **Union[Dict, List[Tuple[Dict, Dict]]]**
- When a **Dict** is provided, encodes a single Protobuf message according to the given protobuf type definition in `blackboxprotobuf` format.

- When a **List[Tuple[Dict, Dict]]** is provided, treats it as a stream of multiple Protobuf message segments, where each tuple contains `(segment_data, typedef)`. The method will encode each segment separately and concatenate them into a single gRPC framed stream.

    **is_gzip**: **bool=False** - Whether to compress the Protobuf payload using gzip.

**Returns**: Returns the updated `HttpRequest` object with its `data` field replaced by a fully framed gRPC binary message or a concatenated gRPC framed binary stream.

**Example:**
Single message encoding:

```python
yield HttpRequest(
    data={...}, # Define plain Protobuf data first
).grpc_encode(typedef_or_stream={...}, is_gzip=False) # Then encode it with a typedef
```

Multiple message streaming encoding:

```python
yield HttpRequest(
    data=None, # Can be omitted or None; if provided, it will be overwritten in streaming mode.
).grpc_encode(
    typedef_or_stream=[
        (segment_data1, typedef1),
        (segment_data2, typedef2),
        (segment_data3, typedef3),
        ...
    ],
    is_gzip=False
)
```

✅ This design makes request construction **cleaner and declarative**, while keeping encoding logic modular and optional. You can freely decide when and whether to apply gRPC framing — without mixing protocol-specific details directly into the `Request`.


**Notes:**
- In rare edge cases (e.g., large binary blobs or concatenated datasets), a single gRPC message may exceed the 4 GB limit. To prevent decoding errors or hangs, stream encoding mode enables splitting into framed segments.
- Protobuf encoding with `blackboxprotobuf` is flexible but may be slow for large messages — prioritize correctness over speed.

**Reference:**
> For more details about `blackboxprotobuf`, see: https://github.com/nccgroup/blackboxprotobuf



📦 **gRPC Frame Structure (used in this framework)**
When using `grpc_encode()`, the request body is encoded into a gRPC-compatible binary format. The resulting byte stream follows the standard gRPC framing layout:

- **Byte 1**: Compression flag (`0` = uncompressed, `1` = gzip compressed)
- `Bytes 2–5`: 4-byte unsigned integer (big-endian), indicating the length of the following message body
- `Bytes 6+`: Protobuf-encoded binary payload

This format complies with the official gRPC-over-HTTP/2 wire protocol and is fully compatible with standard gRPC servers.

❓ **Message Size Limit**
The 4-byte length field enforces a maximum message size of approximately 4 GB (`2^32 - 1` bytes). This limit is a protocol constraint and **cannot be changed by configuration**.

🔧 **Handling Messages Larger than 4 GB**
- ✅ **Recommended**: Use gRPC Streaming RPC
Split the payload into multiple Protobuf messages and pass them as a list of `(data, typedef)` tuples to `grpc_encode()`.
Each segment will be encoded as an individual gRPC frame, concatenated into a valid streaming-compatible binary sequence.
This approach avoids size constraints and retains full protocol compatibility.

- ⚠️ **Not recommended**: Manually crafting oversized HTTP/2 frames

Attempting to bypass the gRPC framing limit (e.g., by hacking raw HTTP/2 transport) is non-standard and **strongly discouraged**. It may cause undefined behavior, decoder hangs, or outright rejection by compliant gRPC servers.

> This is why the framework natively supports gRPC streaming format — **not just for spec compliance, but also for stability and correctness in large-scale data scenarios**.

📘 **Reference:**
According to the gRPC wire protocol:
> “Each message is preceded by a compressed-flag byte and a 4-byte big-endian message length.”



## 2.3 WebSocketRequest
### 2.3.1 Attributes
| Attribute | Description |
| --------- | ----------- |
| **websocket_id** | Identifier for an existing WebSocket session (for reuse). Not required for initial connection. |
| **send_message** | Message to send over the WebSocket connection. A single message will be automatically wrapped as `[message]`. You may also pass a list to send multiple messages in a single request. (Since version ≥ 0.2.2, each message must be wrapped in a `WebSocketMsg` object, because in WebSocket communication, messages are not always byte streams — `WebSocketMsg` provides a one-to-one mapping between message content and its type.)  |
| **ping_data** | User-level ping data. Some connections define custom ping content; maintaining this in the crawler layer would be inconvenient, so the framework implements internal management for it (configured when the WebSocket is established and cannot be changed afterward). This field applies only to user-defined pings and has no effect on protocol-level pings (which are handled internally by the underlying `curl_cff`). Like `send_message`, the value should be wrapped in `WebSocketMsg`, but without the `[message]` list form. |
| **ping_interval** | Interval between ping messages. |

### 2.3.2 Methods
#### 2.3.2.1 protobuf_encode(self, typedef_or_stream: Union[Dict, List[Tuple[Dict, Dict]]])
Encodes the request’s `send_message` into Protobuf format and returns the updated request object (chainable).

**Parameters**: 
    **typedef_or_stream**: **Union[Dict, List[Tuple[Dict, Dict]]]**
- **Dict**: Encodes only the first message in `send_message`. The encoded content replaces `send_message`, and all other messages are discarded.

- **List[Tuple[Dict, Dict]]**: Treated as a sequence of Protobuf message segments. Each tuple is `(segment_data, typedef)`, and each segment is encoded separately.

**Returns**: The updated `WebSocketRequest` object with its `send_message` field replaced.

**Example:**
Single message encoding:
```python
yield WebSocketRequest(
    send_message=[...], # Define plain Protobuf data first
).protobuf_encode(typedef_or_stream={...}) # Then encode it with a typedef
```

Multiple message streaming encoding:
```python
yield WebSocketRequest(
    send_message=None, # Can be omitted or None; if provided, it will be overwritten.
).protobuf_encode(
    typedef_or_stream=[
        (msg1, typedef1),
        (msg2, typedef2),
        (msg3, typedef3),
        ...
    ]
)
```



#### 2.3.2.2 grpc_encode(self, typedef_or_stream: Union[Dict, List[Tuple[Dict, Dict]]], is_gzip: bool=False)
Same as `protobuf_encode`, but with additional support for the `is_gzip` parameter to enable Gzip compression.

#### 2.3.2.3 grpc_stream_encode(self, typedef_or_stream: Union[Dict, List[Tuple[Dict, Dict]]], is_gzip: bool=False)
Similar to `HttpRequest.grpc_encode` in `List[Tuple[Dict, Dict]]` mode.

However, due to two key limitations:
1. **WebSocket streaming complexity** — it would require an additional nesting layer for proper framing.
2. **CPU-bound encoding overhead** — since the framework is asynchronous and single-threaded, large stream-encoding tasks cannot be accelerated within the event loop.

The framework therefore **only supports encoding into a single message**.

If you need to send multiple gRPC stream messages within a single `WebSocketRequest`, you should **manually encode them and pass them directly to `send_message`**. This approach keeps message handling explicit, avoids ambiguity at the framework level, and is the **recommended practice**.

👉 For performance, CPU-intensive encoding should be delegated to worker threads. Once encoding is complete, the result can be passed directly to `send_message`.


**Notes**:
Starting from version >=0.2.2, `protobuf_encode` and `grpc_encode` are bound to each individual `WebSocketMsg` rather than the `WebSocketRequest` object.

The `grpc_stream_encode` method now encodes and concatenates all byte messages from `send_message` into a single streaming byte message. Since protobuf/grpc encoding is already handled within `WebSocketMsg`, `grpc_stream_encode` no longer accepts input parameters.

The first argument to `ws.send` must be `bytes`. Use the framework-owned
`from scrapy_cffi.platform import WebSocketFlag`; the curl adapter converts it
to the vendor-specific flag. Existing `CurlWsFlag` values remain accepted.

Example:
```python
from scrapy_cffi.platform import WebSocketFlag

yield WebSocketRequest(
    send_message=[
        WebSocketMsg(data={"1": b"hello"}, flags=WebSocketFlag.BINARY).protobuf_encode(typedef={"1": "bytes"}),
        WebSocketMsg(data=b"hi", flags=WebSocketFlag.BINARY),
    ]
).grpc_stream_encode()
```



### 2.3.3 WebSocket Communication Behavior
WebSocket communication is based on a single persistent connection that allows multiple messages to be sent and received over time. In this framework, all WebSocket interactions—regardless of the number of messages—are uniformly represented using the WebSocketRequest class. There is no need to distinguish between initial or subsequent messages, as they all share the same request structure.

However, in some cases, a website may expect a message to be sent immediately after the WebSocket connection is established. If no message is sent within a very short time, the server might close the connection prematurely. To handle such scenarios, the framework allows you to configure some initial messages that is automatically sent as soon as the connection is established.

The framework therefore deliberately keeps connection establishment and its
initial `send_message` on the same `WebSocketRequest`. After connecting, those
messages are sent before the first receive operation.

Incoming frames are dispatched directly to the request callback. A long-lived
listener remains active until the user stops it, the peer closes it, or the
crawler shuts down; no queue-end sentinel is involved. Stop explicitly from a
callback when the spider has collected enough data:

```python
async def parse_socket(self, response: WebSocketResponse):
    yield {"message": response.msg}
    if self.enough_data:
        response.stop_listening()
```

`CloseSignal(websocket_end_for_key=...)` remains supported for compatibility,
but new spiders should prefer the response control because it expresses the
connection lifecycle at the callback that owns the decision.



## 2.4 MediaRequest
`MediaRequest` is a subclass of `HttpRequest` for sequential ranged downloads
of image, audio, or video bodies. It runs on the existing crawler event loop and
does not create worker tasks, threads, or parallel range requests.

When `media_size > 0`, the downloader requests inclusive byte ranges in order
and combines them into the ordinary buffered response. When `media_size == 0`,
it performs one normal request because it cannot safely invent range bounds.
The original request headers are never mutated.

### 2.4.1 Attributes
| Attribute | Description |
| --------- | ----------- |
| **single_part_size** | Positive size in bytes of each sequential range. |
| **media_size** | Known total byte size, or `0` for one ordinary request. |
| **max_media_size** | Optional positive in-memory download bound. |


---


# 3.Response Objects
`scrapy_cffi` provides two types of response objects: `HttpResponse` and `WebSocketResponse`.

## 3.1 Response
A shared superclass for `HttpResponse` and `WebSocketResponse`, used as the unified response interface within the framework.

### 3.3.1 Attributes
Common Attributes:
| Attribute | Description |
| --------- | ----------- |
| **session_id** | Session ID tied to this response (for reuse) |
| **raw_response** | Raw `curl_cffi` response object |
| **meta** | Metadata passed from the request |
| **dont_filter** | Carries over from the request |
| **callback** | Carries over from the request |
| **errback** | Carries over from the request |
| **desc_text** | Description from the request |
| **request** | The original request object |

## 3.2 HttpResponse
### 3.2.1 Attributes
| Attribute | Description |
| --------- | ----------- |
| **status_code** | HTTP status code |
| **content** | Response body in bytes |
| **text** | Response body as string |

### 3.2.2 Methods
`scrapy_cffi` automatically binds a `Selector` to each `HttpResponse`, providing a Scrapy-like parsing interface with enhanced capabilities:
#### 3.2.2.1 xpath(query)
#### 3.2.2.2 css(query)
#### 3.2.2.3 re(query)
Example 1:
```html
<html>
  <body>
    <h1>Main Title</h1>
    <ul>
      <li><a href="/link1">Link 1</a></li>
      <li><a href="/link2">Link 2</a></li>
    </ul>
  </body>
</html>
```

```python
async def parse(self, response: HttpResponse):
    # .get() -> Return the first extracted result as a string. Equivalent to extract_first().
    # .getall() -> Return all extracted results as a list of strings. Equivalent to extract().
    print(response.css("h1::text").get())           # => Main Title
    print(response.css("a::text").getall())         # => ['Link 1', 'Link 2']
    print(response.css("a::attr(href)").getall())   # => ['/link1', '/link2']

    print(response.xpath("//h1/text()").get())          # => Main Title
    print(response.xpath("//ul/li/a/text()").getall())  # => ['Link 1', 'Link 2']
```

Example 2:
```html
<html>
  <body>
    <div class="price">$123.45</div>
    <div class="price">$67.89</div>
  </body>
</html>
```

```python
async def parse(self, response: HttpResponse):
    # .re_first(regex) -> Apply a regular expression and return only the first match, or None.
    # .attrib-> Access the tag attributes as a dictionary (only available when selecting elements directly).
    print(response.css("div.price::text").re(r"\$(\d+\.\d+)"))          # => ['123.45', '67.89']
    print(response.css("div.price::text").re_first(r"\$(\d+\.\d+)"))    # => '123.45'
```

#### 3.2.2.4 json()
Shortcut for `raw_response.json()`.

#### 3.2.2.5 extract_json(key: str, re_rule: str="")
Extracts standard JSON from text content (for cases where JSON is embedded in HTML or returned as text).

**Parameters**: 
    **key**: **str** — key to search in parsed JSON objects
    **re_rule**: **str** — optional regex to extract JSON strings directly

**Returns**: `Union[List[Union[Dict, str]], Dict, str]` If no key is provided, all matched JSON blocks are returned. If only one match is found, a single object is returned instead of a list.

Example:
```python
# Given the following response.text:
response.text = """
<html>
  <head>...</head>
  <body>
    <div ...>
        {
            "a": 1,
            "b": "2",
            "c": [0, "3", {"_a": 4, "_b": "5"}],
            "d": {"d0": 6, "d1": "7"}
        }
    </div>
    {
        "a": {"d0": 14, "d2": "15"},
        "e": 8,
        "f": "9",
        "g": [10, "11", {"_a": 12, "_b": "13"}]
    }
  </body>
</html>
"""
async def parse(self, response: HttpResponse):
    print(response.extract_json(key="a"))   # => [{'d0': 14, 'd2': '15'}, 1]
    print(response.extract_json(key="_a"))  # => [4, 12]
    print(response.extract_json(key="c"))   # => [[[0, '3', {'_a': 4, '_b': '5'}]]
    print(response.extract_json(key="e"))   # => 8
```

#### 3.2.2.6 extract_json_strong(key: str, strict_level=2, re_rule="")
Use this function when the response contains **non-standard** or malformed JSON. It performs recursive global scanning and is more tolerant of:

- Extra or missing braces
- JavaScript-style comments
- Unquoted strings
- Nested JSON strings

This method is more powerful but slightly slower, especially when strict_level=0 (loose JSON5 mode).

**Parameters:**
    Same as `extract_json`
    **strict_level**: Literal[0, 1, 2]
- `2`, Use `orjson` (fastest, strictest)
- `1`, Use Python's built-in `json` module
- `0`, Use `json5` for maximum leniency (e.g., support for comments and missing quotes)

**Returns**: Same structure as `extract_json`

Example:
```python
# Sample response.text with embedded comments, quote issues, and nested JSON-as-string:
response.text = """
    <html>
        <head>...</head>
        <body>
            "{"
            <div ... class="{">
                {
                    "a": 1,
                    "b": "2",
                    "c": [0, "3", {"_a": 4, "_b": "5"}],
                    "d": {"d0": 6, "d1": "7"},
                    "level1": {
                        "raw": "{\\"key\\": {\\"deep\\": \\"value\\"}}"
                    }
                }
                "{"
                <div ... class="{">
                    {
                        "a": {"d0": 14, "d2": "15"},
                        "e": 8,
                        "f": "9",
                        "g": [10, "11", {"_a": 12, "_b": "13"}],
                        "logs": [
                            "{\\"event\\": \\"click\\", \\"meta\\": {\\"target\\": \\"button\\"}}",
                            "{\\"event\\": \\"scroll\\", \\"meta\\": {\\"target\\": \\"window\\"}}"
                        ]
                    }
                </div>
            </div>
            {
                "h": {"d0": 16, "d2": "17"}, // no quotes!
                "e": 18,
                "i": "19,
                "j": [20, "21", {"_a": 22, "_b": "23"}],
                "logs": [
                    "{\\"event\\": \\"click\\", \\"meta\\": {\\"target\\": \\"button\\"}}",
                    "{\\"event\\": \\"scroll\\", \\"meta\\": {\\"target\\": \\"window\\"}}"
                ]
            }
            "}"
            {
                "k": {"d0": 24, "d2": "25"},
                "l": 26,
                "m": "27,
                "n": [28, "29", {"_a": 30, "_b": "31"}],
                "o": '{bad: "json"}',
            "}"
        </body>
    </html>
"""
async def parse(self, response: HttpResponse):
    # extract_json
    print(response.extract_json(key="a"))           # => [{'d0': 14, 'd2': '15'}, 1]
    print(response.extract_json(key="_a"))          # => [4, 12, 22, 30]
    print(response.extract_json(key="c"))           # => [0, '3', {'_a': 4, '_b': '5'}]
    print(response.extract_json(key="e"))           # => [8, 18]
    print(response.extract_json(key="raw"))         # => []
    print(response.extract_json(key="key"))         # => []
    print(response.extract_json(key="deep"))        # => []
    print(response.extract_json(key="event"))       # => []
    print(response.extract_json(key="target"))      # => []

    # extract_json_strong
    print(response.extract_json_strong(key="a"))     # => [1, {'d0': 14, 'd2': '15'}]
    print(response.extract_json_strong(key="_a"))    # => [4, 12, 22, 30]
    print(response.extract_json_strong(key="c"))     # => [0, '3', {'_a': 4, '_b': '5'}]
    print(response.extract_json_strong(key="e"))     # => 8
    # Why is `"18"` missing here?
    # Because the adjacent field, e.g., `"i": "19,`, is malformed JSON (missing a closing quote),
    # which causes the entire JSON block to become invalid and unparseable—even for tolerant parsers.
    # This also implies that the `extract_json()` function may mistakenly extract or include
    # invalid JSON fragments, leading to partial or incorrect data.

    print(response.extract_json_strong(key="raw"))       # => {"key": {"deep": "value"}}
    print(response.extract_json_strong(key="key"))       # => {'deep': 'value'}
    print(response.extract_json_strong(key="deep"))      # => value
    print(response.extract_json_strong(key="event"))     # => ['click', 'scroll']
    print(response.extract_json_strong(key="target"))    # => ['button', 'window']
```

#### 3.2.2.7 extract_json_chain(keys: List[str], strict_level=2, re_rule="")
Use chain scanning when you want to search keys in order instead of searching one key globally:

```python
async def parse(self, response: HttpResponse):
    ids = response.extract_json_chain(keys=["payload", "items", "id"])
```

The scanner extracts all `payload` values first, scans only those values for `items`, then scans only those values for `id`. Each layer is deduplicated.

**Question**: 
Should I always use `extract_json_strong` since it's more powerful?

**Answer**: 
The `extract_json` function is based on regular expression matching, while `extract_json_strong` uses global recursive string scanning. To handle complex scenarios, `extract_json_strong` applies many special heuristics, which makes it slightly slower in performance — especially when `strict_level=0` is enabled (which allows JSON5-like syntax).  

Therefore, when the response text is standard JSON, you should prefer using `extract_json`. When `extract_json_strong` is necessary, it's recommended to first extract the top-level keys of the data and then access the desired values via dictionary traversal. This approach minimizes the use of `extract_json_strong` and yields better performance.

#### 3.2.2.8 protobuf_decode
Decodes a Protobuf message from the given `content` (or `msg` for WebSocket) using `blackboxprotobuf`. Returns a tuple `(data, typedef)`.

```python
data, typedef = response.protobuf_decode()
```

#### 3.2.2.9 grpc_decode
Decodes one or more gRPC-framed messages from the HTTP response (`response.content`). This method parses the standard gRPC frame format — including the 1-byte compression flag, 4-byte big-endian length prefix, and Protobuf-encoded message — and returns the decoded content using `blackboxprotobuf`.

**Returns**: `Union[Tuple[Dict, Dict], List[Tuple[Dict, Dict]]]`
- If the response contains **a single message**, returns a (data, typedef) tuple.
- If the response contains **multiple concatenated gRPC messages** (i.e., stream-style response), returns a `List[(data, typedef)]`.

    This behavior is automatically determined based on the binary content.

**Examples:**
Single message decoding:
```python
data, typedef = response.grpc_decode()
```

Streaming message decoding:
```python
results = response.grpc_stream_decode() # Automatically returns a list if multiple messages detected
for data, typedef in results:
    print(data)
    print(typedef)
```

## 3.3 WebSocketResponse
### 3.3.1 Attributes
| Attribute | Description |
| --------- | ----------- |
| **websocket_id** | Unique WebSocket session ID for reuse |
| **msg** | The message received over the WebSocket |

### 3.3.2 Methods
#### 3.3.2.1 stop_listening

Requests idempotent shutdown of the long-lived listener. This is a synchronous
control method; call it directly from the async callback without `await`.

#### 3.3.2.2 protobuf_decode
#### 3.3.2.3 grpc_decode
same as in `HttpResponse`, but applies to msg.
