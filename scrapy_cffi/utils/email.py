"""Send SMTP email without blocking an asyncio worker event loop."""

import asyncio
import smtplib
from email.header import Header
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional, Sequence, Union

MsgType = Union[EmailMessage, MIMEText, MIMEMultipart]


class Email:
    """Provide lazy synchronous SMTP and asyncio-friendly send operations."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        authorization_code: str,
        *,
        use_ssl: bool = True,
        starttls: bool = False,
        timeout: float = 10.0,
    ) -> None:
        """Store SMTP connection settings without opening a socket."""
        if use_ssl and starttls:
            raise ValueError("use_ssl and starttls cannot both be enabled")
        self.host = host
        self.port = port
        self.username = username
        self.authorization_code = authorization_code
        self.use_ssl = use_ssl
        self.starttls = starttls
        self.timeout = timeout
        self.smtp_obj: Optional[smtplib.SMTP] = None

    def _connect(self) -> smtplib.SMTP:
        """Open and authenticate one SMTP connection."""
        smtp_cls = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
        smtp_obj = smtp_cls(self.host, self.port, timeout=self.timeout)
        if self.starttls:
            smtp_obj.starttls()
        if self.username:
            smtp_obj.login(self.username, self.authorization_code)
        return smtp_obj

    def login(self) -> None:
        """Open a reusable compatibility connection on explicit request."""
        self.close()
        self.smtp_obj = self._connect()

    def close(self) -> None:
        """Close an explicitly opened compatibility connection."""
        if self.smtp_obj is None:
            return
        try:
            self.smtp_obj.quit()
        finally:
            self.smtp_obj = None

    @staticmethod
    def set_headers(
        msg: MsgType,
        sender_name: str,
        sender_email: str,
        receiver_name: str,
        receiver_email: str,
        subject: str,
    ) -> MsgType:
        """Set compatible display-name and subject headers on a message."""
        msg["From"] = formataddr((str(Header(sender_name, "utf-8")), sender_email))
        msg["To"] = formataddr((str(Header(receiver_name, "utf-8")), receiver_email))
        msg["Subject"] = str(Header(subject, "utf-8"))
        return msg

    @staticmethod
    def create_message(
        subject: str,
        body: str,
        sender: str,
        to_addrs: Sequence[str],
        *,
        html: Optional[str] = None,
    ) -> EmailMessage:
        """Build a UTF-8 text message with an optional HTML alternative."""
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = ", ".join(to_addrs)
        message.set_content(body)
        if html is not None:
            message.add_alternative(html, subtype="html")
        return message

    def _send_once(
        self,
        msg: Union[MsgType, str],
        to_addrs: Union[str, Sequence[str]],
    ) -> None:
        """Send through one isolated SMTP connection and always close it."""
        raw_msg = msg.as_string() if not isinstance(msg, str) else msg
        smtp_obj = self._connect()
        try:
            smtp_obj.sendmail(self.username, to_addrs, raw_msg)
        finally:
            try:
                smtp_obj.quit()
            except smtplib.SMTPException:
                smtp_obj.close()

    def send(
        self,
        msg: Union[MsgType, str],
        to_addrs: Union[str, Sequence[str]],
    ) -> None:
        """Send synchronously, reusing only an explicitly opened connection."""
        if self.smtp_obj is None:
            self._send_once(msg, to_addrs)
            return
        raw_msg = msg.as_string() if not isinstance(msg, str) else msg
        self.smtp_obj.sendmail(self.username, to_addrs, raw_msg)

    async def send_async(
        self,
        msg: Union[MsgType, str],
        to_addrs: Union[str, Sequence[str]],
    ) -> None:
        """Send on the default worker thread without blocking asyncio."""
        await asyncio.to_thread(self._send_once, msg, to_addrs)

    async def send_text_async(
        self,
        subject: str,
        body: str,
        to_addrs: Sequence[str],
        *,
        sender: Optional[str] = None,
        html: Optional[str] = None,
    ) -> None:
        """Build and asynchronously send one text or multipart message."""
        message = self.create_message(
            subject,
            body,
            sender or self.username,
            to_addrs,
            html=html,
        )
        await self.send_async(message, to_addrs)

    def __enter__(self) -> "Email":
        """Open the compatibility connection for a synchronous context."""
        self.login()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Close the compatibility connection when leaving its context."""
        self.close()


__all__ = ["Email", "MsgType"]
