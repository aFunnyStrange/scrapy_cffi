import asyncio
import inspect
from tenacity import retry, wait_fixed, retry_if_exception_type
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

def auto_retry(func: Callable):
    @wraps(func)
    @retry(
        wait=wait_fixed(1),
        retry=retry_if_exception_type((OperationalError, DBAPIError)),
        reraise=True
    )
    async def wrapper(self, *args, **kwargs):
        if args[0].stop_event.is_set():
            raise asyncio.CancelledError("Stop event set, abort SQLAlchemy operation")
        try:
            return await func(*args, **kwargs)
        except (OperationalError, DBAPIError):
            if args[0].stop_event.is_set():
                raise asyncio.CancelledError("Stop event set during reconnect")
            await args[0]._reconnect()
            return await func(*args, **kwargs)
    return wrapper


class SQLAlchemyMySQLManager:
    def __init__(self, stop_event, host, port, user, password, db):
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

    """
    execute	执行修改数据库的 SQL 语句	None	插入、更新、删除、DDL 等无查询结果操作
    fetchone	执行查询，取回一条记录	单条记录（元组或映射）	预期只返回一条结果的查询
    fetchall	执行查询，取回所有记录	记录列表	需要获取多条查询结果的场景
    """

    @auto_retry
    async def execute(self, sql: str, params: Optional[dict[str, Any]] = None) -> None:
        async with self.session_factory() as session:
            await session.execute(text(sql), params)
            await session.commit()

    @auto_retry
    async def fetchone(self, sql: str, params: Optional[dict[str, Any]] = None) -> Optional[Any]:
        async with self.session_factory() as session:
            result = await session.execute(text(sql), params)
            return result.fetchone()

    @auto_retry
    async def fetchall(self, sql: str, params: Optional[dict[str, Any]] = None) -> list[Any]:
        async with self.session_factory() as session:
            result = await session.execute(text(sql), params)
            return result.fetchall()

    async def close(self):
        if self.engine:
            await self.engine.dispose()
