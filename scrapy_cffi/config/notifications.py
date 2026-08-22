"""Define optional email and crawler-monitoring configuration."""

from typing import List, Optional

from pydantic import Field, SecretStr, model_validator

from ..models import StrictValidatedModel


class EmailInfo(StrictValidatedModel):
    """Configure the explicitly registered email notification extension."""

    HOST: str = ""
    PORT: int = Field(default=465, ge=1, le=65535)
    USERNAME: str = ""
    PASSWORD: SecretStr = SecretStr("")
    FROM_ADDRESS: str = ""
    TO_ADDRESSES: List[str] = Field(default_factory=list)
    USE_SSL: bool = True
    STARTTLS: bool = False
    TIMEOUT: float = Field(default=10.0, gt=0)
    SUBJECT_PREFIX: str = "[scrapy-cffi]"
    SEND_ON_ENGINE_STOPPED: bool = True
    SEND_ON_ERROR: bool = False

    @model_validator(mode="after")
    def validate_transport(self) -> "EmailInfo":
        """Reject mutually exclusive implicit TLS and STARTTLS modes."""
        if self.USE_SSL and self.STARTTLS:
            raise ValueError("EMAIL_INFO cannot enable USE_SSL and STARTTLS together")
        return self


class MonitorInfo(StrictValidatedModel):
    """Configure an explicitly registered crawler monitor extension."""

    HUB_URL: str = "http://127.0.0.1:6800"
    WORKER_ID: Optional[str] = None
    EVENT_BATCH_SIZE: int = Field(default=100, ge=1)
    HEARTBEAT_INTERVAL: float = Field(default=15.0, gt=0)
    TIMEOUT: float = Field(default=3.0, gt=0)


__all__ = ["EmailInfo", "MonitorInfo"]
