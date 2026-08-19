# 1.Introduction
To ensure stability, `scrapy_cffi` provides a **hooks extension system** for user-level components. This system allows users to extend behavior without exposing core internals, giving access to necessary operations for user-level components. Hooks are stored in the `hooks` attribute of each user-level component, including spiders, pipelines, interceptors, and extensions.

**Design Philosophy**
Hooks are designed to provide **controlled extensibility**, enabling plugin-style behavior while preserving encapsulation.

**Key Design Notes**:
- Hooks are organized by **component responsibility**, e.g., `self.hooks.session`.
- Each hook exposes only **selected callable functions**, not direct access to core internals.
- Benefits of this design:
    - Clean separation of concerns.
    - Safe, controlled interaction with internal components.
    - Easier extensibility through external plugins.

---

# 2.Spider
## 2.1 Session
Session-related hooks are accessed via `self.hooks.session`.
### 2.1.1 `register_sessions`
Allows batch registration of accounts and cookies at the spider level. The framework automatically maintains session states.

**Parameters**:
- `user_cookies: Dict[str, Dict]` – a dictionary mapping user identifiers to cookie dictionaries.
- `group_id: Optional[str] = None` – optional group identifier.

**Returns**:
- `str` – the session_id of this session group.

**Description**:
- Registers multiple user sessions under a single logical group called `session_id`. Requests using the `session_id` will **randomly rotate** among associated sessions.

**Note**:
- Designed for scenarios requiring random session rotation.
- Using `session_id` for `websocket` communication may produce unexpected behavior, as each request could use a different session.

**Usage Example**:
```python 
# Register multiple cookie sessions
session_id = self.hooks.session.register_sessions({
    "user1": "cookies_dict1",
    "user2": "cookies_dict2",
    "user3": "cookies_dict3",
    "user4": "cookies_dict4"
})
# Use that session_id in requests
yield HttpRequest(
    session_id=session_id,
    ...
)
```

### 2.1.2 `get_session_cookies`
Retrieve cookies of a session immediately by `session_id`, without waiting for session termination.

**Purpose**:
- Simulate multiple user identities.
- Rotate between different cookie pools for login-required pages.
- Avoid frequent login requests.

**Parameters**:
- `session_id: str` – the ID of the session to retrieve cookies from.

**Returns**:
- `dict` – cookies dictionary; empty if no cookies are available.

---

# 3.Pipeline
## 3.1 Session
### 3.1.1 `get_session_cookies`
Same as **2.1.2** Section.

## 3.1 Signals
Signal-related hooks are accessed via `self.hooks.signals`.
### 3.1.1 send
**Parameters**:
- `signal: object` – the signal object.
- `data: SignalInfo` – the signal payload to send.

**Returns**:
- `None`

**Description**:
Some signals like `item_dropped` or `item_error` cannot be automatically detected by the framework because they depend on user data operations. Users must manually send these signals from their pipelines to the framework’s signal system.

---

# 4.Interceptor
No hook plugins are currently provided for interceptors.

---

# 5.Extension
## 5.1 Signals
Signal-related hooks are accessed via `self.hooks.signals`.
### 5.1.1 connect
Registers an extension callback. Refer to the project template extensions for examples.

**Parameters**:
- `signal: object` – the signal to connect to.
- `callback: SignalCallback` – the callable callback function.
```python
SignalCallback = Union[Callable[[T], Any], Callable[[T], Awaitable[Any]]]
```

**Returns**:
- `None`

---

If you have specific feature requests not yet provided, please participate in the [discussions](https://github.com/aFunnyStrange/scrapy_cffi/discussions) to share your ideas.