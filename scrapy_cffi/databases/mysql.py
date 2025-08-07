import asyncio
import inspect
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception, RetryError
from functools import wraps
from typing import TYPE_CHECKING, Optional, Any, Callable
try:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
    from sqlalchemy.exc import DBAPIError, OperationalError
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
except ImportError as e:
    raise ImportError(
        "Missing SQLAlchemy async dependencies. "
        "Please install: pip install sqlalchemy[asyncio] aiomysql"
    ) from e
if TYPE_CHECKING:
    from ..crawler import Crawler
    from sqlalchemy.sql import Executable

def is_fatal_error(msg: str) -> bool:
    return (
        "unknown database" in msg or
        "access denied" in msg or
        "doesn't exist" in msg
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
            reraise=True
        )
        async def _inner():
            if self.stop_event.is_set():
                raise asyncio.CancelledError("Stop event set, abort SQLAlchemy operation")
            try:
                return await func(self, *args, **kwargs)
            except (OperationalError, DBAPIError) as e:
                msg = str(e).lower()
                if is_fatal_error(msg):
                    print(f"[MySQL] error: {msg}")
                    self.stop_event.set()
                    raise asyncio.CancelledError("Fatal DB error, stopping all tasks")
                await self._reconnect()
                raise e
        try:
            return await _inner()
        except RetryError as e:
            print(f"[MySQL] reconnect failed：{e.last_attempt.exception()}")
            self.stop_event.set()
            raise e.last_attempt.exception()
    return wrapper

class SQLAlchemyMySQLManager:
    def __init__(self, stop_event, host, port, db, user, password):
        self.stop_event = stop_event
        self._db_url = f"mysql+aiomysql://{user}:{password}@{host}:{port}/{db}"
        self._method_cache = {}
        self.engine: Optional[AsyncEngine] = None
        self.session_factory = None

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            host=crawler.settings.MYSQL_INFO.HOST,
            port=crawler.settings.MYSQL_INFO.PORT,
            user=crawler.settings.MYSQL_INFO.USERNAME,
            password=crawler.settings.MYSQL_INFO.PASSWORD,
            db=crawler.settings.MYSQL_INFO.DB,
        )

    async def init(self):
        await self._reconnect()

    async def _reconnect(self):
        if self.engine:
            await self.engine.dispose()

        self.engine = create_async_engine(self._db_url, echo=False, pool_pre_ping=True) # echo: debug log
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
                    raise asyncio.CancelledError(f"Stop event set, abort SQLAlchemy operation: {name}")
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
    async def execute(self, sql: str, params: Optional[dict[str, Any]] = None) -> None:
        """modify"""
        async with self.session_factory() as session:
            session: AsyncSession
            await session.execute(text(sql), params)
            await session.commit()

    @auto_retry
    async def fetchone(self, sql: str, params: Optional[dict[str, Any]] = None) -> Optional[Any]:
        """search one"""
        async with self.session_factory() as session:
            session: AsyncSession
            result = await session.execute(text(sql), params)
            return result.fetchone()

    @auto_retry
    async def fetchall(self, sql: str, params: Optional[dict[str, Any]] = None) -> list[Any]:
        """search all"""
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