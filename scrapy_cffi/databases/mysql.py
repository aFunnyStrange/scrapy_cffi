from typing import TYPE_CHECKING

from .sqlalchemy_base import BaseSQLAlchemyManager

if TYPE_CHECKING:
    from ..crawler import Crawler


def _is_fatal_mysql_error(msg: str) -> bool:
    return (
        "unknown database" in msg
        or "access denied" in msg
        or "doesn't exist" in msg
    )


class SQLAlchemyMySQLManager(BaseSQLAlchemyManager):
    def __init__(self, stop_event, db_url: str, engine_kwargs=None):
        super().__init__(
            stop_event=stop_event,
            db_url=db_url,
            engine_kwargs=engine_kwargs,
            label="MySQL",
        )

    def _is_fatal_error(self, msg: str) -> bool:
        return _is_fatal_mysql_error(msg)

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls.from_db_info(crawler, crawler.settings.MYSQL_INFO)
