"""Verify lazy SMTP delivery and opt-in crawler email summaries."""

import asyncio
from types import SimpleNamespace
from typing import List

from scrapy_cffi.extensions.email import EmailNotificationExtension
from scrapy_cffi.extensions.singal_info import SignalInfo
from scrapy_cffi.settings import SettingsInfo
from scrapy_cffi.utils.email import Email


class _FakeSMTP:
    """Record SMTP operations without opening a network socket."""

    instances: List["_FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        """Record connection arguments."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self.logged_in = None
        self.sent = []
        self.closed = False
        type(self).instances.append(self)

    def login(self, username: str, password: str) -> None:
        """Record credentials supplied to the fake server."""
        self.logged_in = (username, password)

    def sendmail(self, sender, recipients, message) -> None:
        """Record one outgoing message."""
        self.sent.append((sender, recipients, message))

    def quit(self) -> None:
        """Record graceful connection closure."""
        self.closed = True

    def close(self) -> None:
        """Record fallback connection closure."""
        self.closed = True


class _SignalHooks:
    """Collect extension callbacks by signal identity."""

    def __init__(self) -> None:
        """Expose the minimal hook shape consumed by extensions."""
        self.callbacks = {}
        self.signals = SimpleNamespace(connect=self.connect)

    def connect(self, signal, callback) -> None:
        """Retain one callback for a signal."""
        self.callbacks[signal] = callback


class _Logger:
    """Capture warning and exception calls for failure isolation tests."""

    def __init__(self) -> None:
        """Initialize empty captured calls."""
        self.warnings = []
        self.exceptions = []

    def warning(self, *args) -> None:
        """Capture one warning call."""
        self.warnings.append(args)

    def exception(self, *args) -> None:
        """Capture one exception call."""
        self.exceptions.append(args)


def test_email_is_lazy_and_async_send_closes_connection(monkeypatch) -> None:
    """Avoid SMTP I/O at construction and offload one bounded send."""
    _FakeSMTP.instances.clear()
    monkeypatch.setattr("scrapy_cffi.utils.email.smtplib.SMTP_SSL", _FakeSMTP)
    sender = Email("smtp.example.com", 465, "bot@example.com", "secret")

    assert _FakeSMTP.instances == []

    message = sender.create_message(
        "Crawler summary",
        "done",
        "bot@example.com",
        ["ops@example.com"],
    )
    asyncio.run(sender.send_async(message, ["ops@example.com"]))

    assert len(_FakeSMTP.instances) == 1
    smtp = _FakeSMTP.instances[0]
    assert smtp.logged_in == ("bot@example.com", "secret")
    assert smtp.sent[0][1] == ["ops@example.com"]
    assert smtp.closed is True


def test_email_extension_is_explicit_and_sends_aggregated_summary() -> None:
    """Count hot events locally and send only the configured stop summary."""

    async def exercise() -> None:
        """Drive the extension callbacks on one event loop."""
        settings = SettingsInfo()
        settings.EMAIL_INFO.HOST = "smtp.example.com"
        settings.EMAIL_INFO.USERNAME = "bot@example.com"
        settings.EMAIL_INFO.TO_ADDRESSES = ["ops@example.com"]
        hooks = _SignalHooks()
        logger = _Logger()
        extension = EmailNotificationExtension.from_crawler(
            hooks,
            settings=settings,
            logger=logger,
        )
        messages = []

        async def send_text_async(subject, body, recipients, **kwargs) -> None:
            """Capture one email without using SMTP."""
            messages.append((subject, body, recipients, kwargs))

        extension.sender.send_text_async = send_text_async
        extension.request_scheduled(SignalInfo())
        extension.response_received(SignalInfo())
        await extension.engine_stopped(SignalInfo())

        assert len(messages) == 1
        assert "crawler stopped" in messages[0][0]
        assert "request_scheduled: 1" in messages[0][1]
        assert messages[0][2] == ["ops@example.com"]
        assert logger.exceptions == []

    asyncio.run(exercise())
