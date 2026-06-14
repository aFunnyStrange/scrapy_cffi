from typing import TYPE_CHECKING

from .sqlalchemy_base import BaseSQLAlchemyManager

if TYPE_CHECKING:
    from ..crawler import Crawler


def _is_fatal_postgres_error(msg: str) -> bool:
    return (
        "database" in msg and "does not exist" in msg
        or "invalid_catalog_name" in msg
        or "password authentication failed" in msg
        or "role" in msg and "does not exist" in msg
    )


class SQLAlchemyPostgresManager(BaseSQLAlchemyManager):
    def __init__(self, stop_event, db_url: str, engine_kwargs=None):
        super().__init__(
            stop_event=stop_event,
            db_url=db_url,
            engine_kwargs=engine_kwargs,
            label="PostgreSQL",
        )

    def _is_fatal_error(self, msg: str) -> bool:
        return _is_fatal_postgres_error(msg)

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls.from_db_info(crawler.stop_event, crawler.settings.POSTGRES_INFO)
