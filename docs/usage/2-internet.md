# 1.Introduction
`scrapy_cffi` is built on top of the `curl_cffi` request library. The primary motivation behind this choice is that `curl_cffi` offers an API that's very similar to the popular `requests` library, making it easier to use.

**Key features of** `curl_cffi`:
- Supports both synchronous and asynchronous requests.
- Handles `HTTP`, `HTTPS`, `WebSocket (WS/WSS)` protocols.
- Allows detailed TLS fingerprint customization, enabling strong `TLS/JA3` fingerprint emulation.





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
allow_redirects: bool = True
max_redirects: int = 30
verify: Optional[bool] = None
impersonate: Optional[BrowserTypeLiteral] = None
ja3: Optional[str] = None
akamai: Optional[str] = None
```

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

Advanced options via `**kwargs` (passed directly to `curl_cffi`, no autocomplete):

```python
proxy: Optional[str] = None
proxy_auth: Optional[Tuple[str, str]] = None
verify: Optional[bool] = None
referer: Optional[str] = None
accept_encoding: Optional[str] = "gzip, deflate, br, zstd"
content_callback: Optional[Callable] = None
extra_fp: Optional[Union[ExtraFingerprints, ExtraFpDict]] = None
thread: Optional[ThreadType] = None
default_headers: Optional[bool] = None
default_encoding: Union[str, Callable[[bytes], str]] = "utf-8"
quote: Union[str, Literal[False]] = ""
curl_options: Optional[dict] = None
http_version: Optional[CurlHttpVersion] = None
debug: bool = False
interface: Optional[str] = None
cert: Optional[Union[str, Tuple[str, str]]] = None
stream: bool = False
max_recv_speed: int = 0
multipart: Optional[CurlMime] = None
```

**Note**: Any unsupported keyword arguments will raise an error.

## 2.2 HttpRequest
### 2.2.1 Attributes
| Attribute | Description |
| --------- | ----------- |
| **method** | HTTP method (`GET`, `POST`, `PUT`, etc.) – case-insensitive |
| **data** | Request body: `Dict`, `List`, `str`, `BytesIO`, or `bytes` |
| **json** | JSON body: `Dict[str, Union[str, int]]` only (bytes not supported) |

### 2.2.2 Methods
#### 2.2.2.1 protobuf_encode(self, typedef: Dict)
Encodes the request body (`data`) into a binary Protobuf payload using the given type definition. The method modifies the request in-place and returns the updated `HttpRequest` object for chaining.
**Parameters**: 
    **typedef**: **Dict** - Protobuf type definition using the `blackboxprotobuf` format.
**Returns**: The updated `HttpRequest` object with its `data` field replaced by the Protobuf-encoded binary payload.

Example:
```python
yield HttpRequest(
    data={...},
).protobuf_encode({...})
```

#### 2.2.2.2 grpc_encode(typedef_or_stream: Union[Dict, List[Tuple[Dict, Dict]]], is_gzip: bool=False)
Encodes the request body (`data`) into a valid gRPC framed message and returns the updated request object for chaining.
**Parameters**: 
    **typedef_or_stream**: **Union[Dict, List[Tuple[Dict, Dict]]]**
        - When a **Dict** is provided, encodes a single Protobuf message according to the given protobuf type definition in `blackboxprotobuf` format.
        - When a **List[Tuple[Dict, Dict]]** is provided, treats it as a stream of multiple Protobuf message segments, where each tuple contains `(segment_data, typedef)`. The method will encode each segment separately and concatenate them into a single gRPC framed stream.
    **is_gzip**: **bool=False** - Whether to compress the Protobuf payload using gzip.
**Returns**: Returns the updated `HttpRequest` object with its `data` field replaced by a fully framed gRPC binary message or a concatenated gRPC framed binary stream.

Example:
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
| **websocket_end** | Indicates that the WebSocket should be closed. |
| **send_message** | Message to send over the WebSocket connection. |

### 2.3.2 Methods
#### 2.3.2.1 protobuf_encode(self, typedef: Dict)
#### 2.3.2.2 grpc_encode(typedef: Dict, is_gzip: bool=False)
same as in `HttpRequest`, but applies to msg.

**WebSocket Communication Behavior**
WebSocket communication is based on a single persistent connection that allows multiple messages to be sent and received over time. In this framework, all WebSocket interactions—regardless of the number of messages—are uniformly represented using the WebSocketRequest class. There is no need to distinguish between initial or subsequent messages, as they all share the same request structure.

However, in some cases, a website may expect a message to be sent immediately after the WebSocket connection is established. If no message is sent within a very short time, the server might close the connection prematurely. To handle such scenarios, the framework allows you to configure an initial message that is automatically sent as soon as the connection is established.

> **Note:**
> Currently, only one initial message can be sent during the connection phase. Support for sending multiple messages immediately after connection will be added in a future version.

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
**Returns**: `List[Union[Dict, str]]` If no key is provided, all matched JSON blocks are returned. If only one match is found, a single object is returned instead of a list.

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

Parameters:
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

**Question**: 
Should I always use `extract_json_strong` since it's more powerful?

**Answer**: 
The `extract_json` function is based on regular expression matching, while `extract_json_strong` uses global recursive string scanning. To handle complex scenarios, `extract_json_strong` applies many special heuristics, which makes it slightly slower in performance — especially when `strict_level=0` is enabled (which allows JSON5-like syntax).  
Therefore, when the response text is standard JSON, you should prefer using `extract_json`. When `extract_json_strong` is necessary, it's recommended to first extract the top-level keys of the data and then access the desired values via dictionary traversal. This approach minimizes the use of `extract_json_strong` and yields better performance.

#### 3.2.2.7 protobuf_decode
Decodes a Protobuf message from the given `content` (or `msg` for WebSocket) using `blackboxprotobuf`. Returns a tuple `(data, typedef)`.

```python
data, typedef = response.protobuf_decode()
```

#### 3.2.2.8 grpc_decode
Decodes one or more gRPC-framed messages from the HTTP response (`response.content`). This method parses the standard gRPC frame format — including the 1-byte compression flag, 4-byte big-endian length prefix, and Protobuf-encoded message — and returns the decoded content using `blackboxprotobuf`.
**Returns**: `Union[Tuple[Dict, Dict], List[Tuple[Dict, Dict]]]`
    - If the response contains **a single message**, returns a (data, typedef) tuple.
    - If the response contains **multiple concatenated gRPC messages** (i.e., stream-style response), returns a `List[(data, typedef)]`.
    This behavior is automatically determined based on the binary content.

Examples:
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
#### 3.3.2.1 protobuf_decode
#### 3.3.2.2 grpc_decode
#### 3.3.2.3 grpc_stream_decode
same as in `HttpResponse`, but applies to msg.