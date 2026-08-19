# Hook 扩展系统

[English](../../en/usage/10-hook.md) | 简体中文

Hook 向用户组件暴露受控能力，而不是泄露核心内部对象。Spider、Pipeline、Interceptor 与 Extension 都通过 `self.hooks` 按职责访问可调用接口。

## Spider Session Hook

### `register_sessions(user_cookies, group_id=None)`

批量注册账号 Cookie，返回一个 Session Group ID。使用该 ID 的普通请求会在组内随机轮换 Session；WebSocket 长连接不适合随机轮换，因为后续请求可能选择不同 Session。

```python
session_id = self.hooks.session.register_sessions({
    "user1": cookies_dict1,
    "user2": cookies_dict2,
})
yield HttpRequest(url=url, session_id=session_id, callback=self.parse)
```

### `get_session_cookies(session_id)`

立即读取 Session 当前 Cookie，不必等待 Session 结束；不存在时返回空字典。Pipeline 也能通过 Session Hook 调用同一接口。

## Pipeline Signal Hook

`self.hooks.signals.send(signal, data)` 用于发送用户负责的 Signal，例如 `item_dropped` 与 `item_error`。

## Interceptor Hook

当前没有专门的 Interceptor Hook 插件。

## Extension Signal Hook

`self.hooks.signals.connect(signal, callback)` 注册同步或异步回调：

```python
SignalCallback = Union[
    Callable[[T], Any],
    Callable[[T], Awaitable[Any]],
]
```

