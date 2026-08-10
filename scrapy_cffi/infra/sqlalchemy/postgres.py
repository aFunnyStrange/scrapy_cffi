"""Provide the PostgreSQL SQLAlchemy transport type."""

from .client import SqlAlchemyClient


class PostgresClient(SqlAlchemyClient):
    """Identify a SQLAlchemy transport configured for PostgreSQL."""


__all__ = ["PostgresClient"]
