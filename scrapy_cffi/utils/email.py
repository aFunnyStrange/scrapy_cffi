import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from typing import Sequence, Union

MsgType = Union[MIMEText, MIMEMultipart]

class Email:
    def __init__(self, host: str, port: int, username: str, authorization_code: str):
        self.host = host
        self.port = port  # 465
        self.username = username
        self.authorization_code = authorization_code  # Not email password
        self.smtp_obj = smtplib.SMTP_SSL(self.host, self.port)
        self.login()

    def login(self) -> None:
        self.smtp_obj.login(self.username, self.authorization_code)

    @staticmethod
    def set_headers(
        msg: MsgType,
        sender_name: str,
        sender_email: str,
        receiver_name: str,
        receiver_email: str,
        subject: str,
    ) -> MsgType:
        msg["From"] = formataddr((str(Header(sender_name, "utf-8")), sender_email))
        msg["To"] = formataddr((str(Header(receiver_name, "utf-8")), receiver_email))
        msg["Subject"] = Header(subject, "utf-8")
        return msg

    def send(self, msg: Union[MsgType, str], to_addrs: Union[str, Sequence[str]]) -> None:
        raw_msg = msg.as_string() if not isinstance(msg, str) else msg
        self.smtp_obj.sendmail(self.username, to_addrs, raw_msg)