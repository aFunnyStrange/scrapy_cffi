"""Implement one-shot SQLAlchemy async engine lifecycle."""

from typing import TYPE_CHECKING, Any, Dict, Optional

try:
    from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
except ImportError as exc:
    raise ImportError(
        "Missing SQLAlchemy async dependencies. Install sqlalchemy[asyncio]."
    ) from exc

if TYPE_CHECKING:
    from ...config.database import SqlAlchemyEngineInfo


def build_engine_kwargs(info: "SqlAlchemyEngineInfo") -> Dict[str, Any]:
    """Map validated settings to SQLAlchemy engine options."""
    return {
        "echo": info.ECHO,
        "pool_pre_ping": info.POOL_PRE_PING,
        "pool_size": info.POOL_SIZE,
        "max_overflow": info.MAX_OVERFLOW,
    }


class SqlAlchemyClient:
    """Own one SQLAlchemy engine without query or retry semantics."""

    def __init__(
        self,
        db_url: str,
        engine_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store engine construction settings without connecting."""
        self._db_url = db_url
        self._engine_kwargs = engine_kwargs or {}
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Any = None

    @classmethod
    def from_info(cls, info: "SqlAlchemyEngineInfo") -> "SqlAlchemyClient":
        """Create a client from validated settings."""
        if not info.resolved_url:
            raise ValueError("%s requires a configured database URL" % cls.__name__)
        return cls(info.resolved_url, build_engine_kwargs(info))

    async def connect(self) -> None:
        """Create the reusable engine and async session factory."""
        if self.engine is not None:
            return
        self.engine = create_async_engine(self._db_url, **self._engine_kwargs)
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )

    async def close(self) -> None:
        """Dispose the engine and clear its session factory."""
        engine = self.engine
        self.engine = None
        self.session_factory = None
        if engine is not None:
            await engine.dispose()


__all__ = ["SqlAlchemyClient", "build_engine_kwargs"]
