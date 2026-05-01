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
        "Please install: pip install sqlalchemy[asyncio] asyncpg"
    ) from e

if TYPE_CHECKING:
    from sqlalchemy.sql import Executable
    from ..crawler import Crawler


def is_fatal_error(msg: str) -> bool:
    return (
        "database" in msg and "does not exist" in msg or
        "invalid_catalog_name" in msg or
        "password authentication failed" in msg or
        "role" in msg and "does not exist" in msg
    )


def is_retryable_db_error(e: Exception) -> bool:
    if isinstance(e, (OperationalError, DBAPIError)):
        msg = str(e).lower()
        if is_fatal_error(msg):
            return False
        return True
    return False


def auto_retry(func: Callable):
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        @retry(
            wait=wait_fixed(1),
            stop=stop_after_attempt(3),
            retry=retry_if_exception(is_retryable_db_error),
            reraise=True,
        )
        async def _inner():
            if self.stop_event.is_set():
                raise asyncio.CancelledError("Stop event set, abort PostgreSQL operation")
            try:
                return await func(self, *args, **kwargs)
            except (OperationalError, DBAPIError) as e:
                msg = str(e).lower()
                if is_fatal_error(msg):
                    print(f"[PostgreSQL] error: {msg}")
                    self.stop_event.set()
                    raise asyncio.CancelledError("Fatal DB error, stopping all tasks")
                await self._reconnect()
                raise e

        try:
            return await _inner()
        except RetryError as e:
            print(f"[PostgreSQL] reconnect failed: {e.last_attempt.exception()}")
            self.stop_event.set()
            raise e.last_attempt.exception()

    return wrapper


class SQLAlchemyPostgresManager:
    def __init__(self, stop_event: asyncio.Event, db_url: str):
        self.stop_event = stop_event
        self._db_url = db_url
        self._method_cache = {}
        self.engine: Optional[AsyncEngine] = None
        self.session_factory = None

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            db_url=crawler.settings.POSTGRES_INFO.resolved_url,
        )

    async def init(self):
        await self._reconnect()

    async def _reconnect(self):
        if self.engine:
            await self.engine.dispose()

        self.engine = create_async_engine(self._db_url, echo=False, pool_pre_ping=True)
        self.session_factory = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    def __getattribute__(self, name: str):
        if name.startswith("_") or name in ("_method_cache", "_reconnect", "stop_event"):
            return super().__getattribute__(name)
        attr = super().__getattribute__(name)
        if not callable(attr) or not inspect.iscoroutinefunction(attr):
            return attr
        method_cache = super().__getattribute__("_method_cache")
        if name not in method_cache:
            @wraps(attr)
            async def wrapper(*args, **kwargs):
                if self.stop_event.is_set():
                    raise asyncio.CancelledError(f"Stop event set, abort PostgreSQL operation: {name}")
                try:
                    return await attr(*args, **kwargs)
                except (OperationalError, DBAPIError):
                    if self.stop_event.is_set():
                        raise asyncio.CancelledError("Stop event set during reconnect")
                    await self._reconnect()
                    return await attr(*args, **kwargs)
            method_cache[name] = wrapper
        return method_cache[name]

    @auto_retry
    async def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> None:
        async with self.session_factory() as session:
            session: AsyncSession
            await session.execute(text(sql), params)
            await session.commit()

    @auto_retry
    async def fetchone(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        async with self.session_factory() as session:
            session: AsyncSession
            result = await session.execute(text(sql), params)
            return result.fetchone()

    @auto_retry
    async def fetchall(self, sql: str, params: Optional[Dict[str, Any]] = None) -> list:
        async with self.session_factory() as session:
            session: AsyncSession
            result = await session.execute(text(sql), params)
            return result.fetchall()

    @auto_retry
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
