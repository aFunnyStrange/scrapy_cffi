import asyncio
import inspect
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from tenacity import RetryError, retry, retry_if_exception, stop_after_attempt, wait_fixed

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
        self._method_cache: Dict[str, Callable] = {}
        self.engine: Optional[AsyncEngine] = None
        self.session_factory = None

    @classmethod
    def from_db_info(cls, crawler: "Crawler", info: "SqlAlchemyEngineInfo"):
        if not info.resolved_url:
            raise ValueError(f"{cls.__name__} requires a configured database URL")
        return cls(
            stop_event=crawler.stop_event,
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

    def _auto_retry(self, func: Callable):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            @retry(
                wait=wait_fixed(1),
                stop=stop_after_attempt(3),
                retry=retry_if_exception(self._is_retryable_db_error),
                reraise=True,
            )
            async def _inner():
                if self.stop_event.is_set():
                    raise asyncio.CancelledError(f"Stop event set, abort {self._label} operation")
                try:
                    return await func(self, *args, **kwargs)
                except (OperationalError, DBAPIError) as e:
                    msg = str(e).lower()
                    if self._is_fatal_error(msg):
                        print(f"[{self._label}] error: {msg}")
                        self.stop_event.set()
                        raise asyncio.CancelledError("Fatal DB error, stopping all tasks")
                    await self._reconnect()
                    raise e

            try:
                return await _inner()
            except RetryError as e:
                print(f"[{self._label}] reconnect failed: {e.last_attempt.exception()}")
                self.stop_event.set()
                raise e.last_attempt.exception()

        return wrapper

    def __getattribute__(self, name: str):
        if name.startswith("_") or name in (
            "_method_cache",
            "_reconnect",
            "stop_event",
            "_auto_retry",
            "init",
            "close",
            "engine",
            "session_factory",
        ):
            return super().__getattribute__(name)
        attr = super().__getattribute__(name)
        if not callable(attr) or not inspect.iscoroutinefunction(attr):
            return attr
        method_cache = super().__getattribute__("_method_cache")
        if name not in method_cache:
            auto_retry = super().__getattribute__("_auto_retry")
            method_cache[name] = auto_retry(attr)
        return method_cache[name]

    async def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> None:
        async with self.session_factory() as session:
            session: AsyncSession
            await session.execute(text(sql), params)
            await session.commit()

    async def fetchone(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        async with self.session_factory() as session:
            session: AsyncSession
            result = await session.execute(text(sql), params)
            return result.fetchone()

    async def fetchall(self, sql: str, params: Optional[Dict[str, Any]] = None) -> list:
        async with self.session_factory() as session:
            session: AsyncSession
            result = await session.execute(text(sql), params)
            return result.fetchall()

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
