"""Provide the MySQL SQLAlchemy transport type."""

from .client import SqlAlchemyClient


class MySQLClient(SqlAlchemyClient):
    """Identify a SQLAlchemy transport configured for MySQL."""


__all__ = ["MySQLClient"]
