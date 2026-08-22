"""Provide opt-in crawler summary and error email notifications."""

from typing import TYPE_CHECKING, Dict

from . import signals
from .base import Extension
from ..utils.email import Email

if TYPE_CHECKING:
    from ..config import EmailInfo
    from ..hooks.signals import SignalsHooks
    from ..settings import SettingsInfo
    from .singal_info import SignalInfo


class EmailNotificationExtension(Extension):
    """Send crawler observations only when explicitly registered in settings."""

    def __init__(self, hooks: "SignalsHooks", **kwargs) -> None:
        """Build the lazy SMTP sender from crawler settings."""
        super().__init__(hooks, **kwargs)
        settings: "SettingsInfo" = kwargs.get("settings")
        if settings is None:
            settings = hooks.settings
        self.logger = kwargs.get("logger")
        if self.logger is None:
            self.logger = hooks.logger
        self.info: "EmailInfo" = settings.EMAIL_INFO
        self.counts: Dict[str, int] = {
            "task_error": 0,
            "spider_error": 0,
            "request_scheduled": 0,
            "response_received": 0,
            "item_scraped": 0,
        }
        self.sender = Email(
            host=self.info.HOST,
            port=self.info.PORT,
            username=self.info.USERNAME,
            authorization_code=self.info.PASSWORD.get_secret_value(),
            use_ssl=self.info.USE_SSL,
            starttls=self.info.STARTTLS,
            timeout=self.info.TIMEOUT,
        )

    @classmethod
    def from_crawler(cls, hooks: "SignalsHooks", **kwargs):
        """Create the extension and subscribe only to required signals."""
        extension = cls(hooks, **kwargs)
        hooks.signals.connect(signals.engine_stopped, extension.engine_stopped)
        hooks.signals.connect(signals.task_error, extension.task_error)
        hooks.signals.connect(signals.spider_error, extension.spider_error)
        hooks.signals.connect(signals.request_scheduled, extension.request_scheduled)
        hooks.signals.connect(signals.response_received, extension.response_received)
        hooks.signals.connect(signals.item_scraped, extension.item_scraped)
        return extension

    def _subject(self, suffix: str) -> str:
        """Build one consistently prefixed notification subject."""
        return "%s %s" % (self.info.SUBJECT_PREFIX, suffix)

    async def _send(self, subject: str, body: str) -> None:
        """Send one notification without allowing SMTP failure to stop work."""
        if not self.info.HOST or not self.info.TO_ADDRESSES:
            self.logger.warning(
                "EmailNotificationExtension requires EMAIL_INFO.HOST and TO_ADDRESSES"
            )
            return
        try:
            await self.sender.send_text_async(
                self._subject(subject),
                body,
                self.info.TO_ADDRESSES,
                sender=self.info.FROM_ADDRESS or self.info.USERNAME,
            )
        except Exception:
            self.logger.exception("Crawler email notification failed")

    async def engine_stopped(self, data: "SignalInfo") -> None:
        """Send one aggregated summary when an engine stops."""
        if not self.info.SEND_ON_ENGINE_STOPPED:
            return
        lines = ["%s: %s" % item for item in sorted(self.counts.items())]
        await self._send("crawler stopped", "\n".join(lines))

    async def task_error(self, data: "SignalInfo") -> None:
        """Count task failures and optionally send an immediate alert."""
        self.counts["task_error"] += 1
        if self.info.SEND_ON_ERROR:
            await self._send("task error", str(data.reason)[:1000])

    async def spider_error(self, data: "SignalInfo") -> None:
        """Count spider failures and optionally send an immediate alert."""
        self.counts["spider_error"] += 1
        if self.info.SEND_ON_ERROR:
            spider_name = getattr(data.spider, "name", "unknown")
            await self._send(
                "spider error",
                "%s: %s" % (spider_name, str(data.exception)[:1000]),
            )

    def request_scheduled(self, data: "SignalInfo") -> None:
        """Count scheduled requests without performing external I/O."""
        self.counts["request_scheduled"] += 1

    def response_received(self, data: "SignalInfo") -> None:
        """Count received responses without performing external I/O."""
        self.counts["response_received"] += 1

    def item_scraped(self, data: "SignalInfo") -> None:
        """Count scraped items without performing external I/O."""
        self.counts["item_scraped"] += 1


__all__ = ["EmailNotificationExtension"]
