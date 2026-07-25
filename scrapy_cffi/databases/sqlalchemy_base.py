import asyncio
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

try:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError, OperationalError
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
except ImportError as e:
    raise ImportError(
        "Missing SQLAlchemy async dependencies. "
        "Please install: pip install sqlalchemy[asyncio]"
    ) from e

if TYPE_CHECKING:
    from sqlalchemy.sql import Executable
    from ..crawler import Crawler
    from ..models.databases import SqlAlchemyEngineInfo
from ..utils.reconnect import AsyncReconnectController, reconnectable


def build_engine_kwargs(info: "SqlAlchemyEngineInfo") -> Dict[str, Any]:
    return {
        "echo": info.ECHO,
        "pool_pre_ping": info.POOL_PRE_PING,
        "pool_size": info.POOL_SIZE,
        "max_overflow": info.MAX_OVERFLOW,
    }


class BaseSQLAlchemyManager:
    """
    Shared async SQLAlchemy manager used by MySQL/PostgreSQL adapters.
    Connection URL and pool options come from *Info models in settings.
    """

    def __init__(
        self,
        stop_event: asyncio.Event,
        db_url: str,
        engine_kwargs: Optional[Dict[str, Any]] = None,
        *,
        label: str = "SQL",
    ):
        self.stop_event = stop_event
        self._db_url = db_url
        self._engine_kwargs = engine_kwargs or {}
        self._label = label
        self.engine: Optional[AsyncEngine] = None
        self.session_factory = None
        self._reconnect_controller = AsyncReconnectController(
            self.stop_event,
            self._reconnect,
            (OperationalError, DBAPIError),
            label=self._label,
            max_attempts=3,
            retry_predicate=self._is_retryable_db_error,
        )

    @classmethod
    def from_db_info(cls, stop_event: asyncio.Event, info: "SqlAlchemyEngineInfo"):
        if not info.resolved_url:
            raise ValueError(f"{cls.__name__} requires a configured database URL")
        return cls(
            stop_event=stop_event,
            db_url=info.resolved_url,
            engine_kwargs=build_engine_kwargs(info),
        )

    async def init(self):
        await self._reconnect()

    async def _reconnect(self):
        if self.engine:
            await self.engine.dispose()
        self.engine = create_async_engine(self._db_url, **self._engine_kwargs)
        self.session_factory = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    def _is_fatal_error(self, msg: str) -> bool:
        return False

    def _is_retryable_db_error(self, e: Exception) -> bool:
        if isinstance(e, (OperationalError, DBAPIError)):
            msg = str(e).lower()
            if self._is_fatal_error(msg):
                return False
            return True
        return False

    @reconnectable
    async def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> None:
        async with self.session_factory() as session:
            session: AsyncSession
            await session.execute(text(sql), params)
            await session.commit()

    @reconnectable
    async def fetchone(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        async with self.session_factory() as session:
            session: AsyncSession
            result = await session.execute(text(sql), params)
            return result.fetchone()

    @reconnectable
    async def fetchall(self, sql: str, params: Optional[Dict[str, Any]] = None) -> list:
        async with self.session_factory() as session:
            session: AsyncSession
            result = await session.execute(text(sql), params)
            return result.fetchall()

    @reconnectable
    async def run_stmt(self, stmt: "Executable", fetch: str = "all") -> Any:
        async with self.session_factory() as session:
            session: AsyncSession
            result = await session.execute(stmt)
            if fetch == "one":
                return result.fetchone()
            elif fetch == "scalar":
                return result.scalar()
            elif fetch == "scalars":
                return result.scalars().all()
            return result.fetchall()

    async def close(self):
        if self.engine:
            await self.engine.dispose()


__all__ = [
    "BaseSQLAlchemyManager",
    "build_engine_kwargs",
]
