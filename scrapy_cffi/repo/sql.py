"""Implement SQL persistence semantics over replaceable SQLAlchemy clients."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import text

from ..infra.sqlalchemy import SqlAlchemyClient
from ..service.resilience import ResourceSlot, RetryPolicy

if TYPE_CHECKING:
    from sqlalchemy.sql import Executable


class SQLRepository:
    """Expose transactional SQL operations with injected retry policy."""

    def __init__(
        self,
        slot: ResourceSlot[SqlAlchemyClient],
        retry_policy: RetryPolicy,
    ) -> None:
        """Bind SQL operations to one replaceable engine slot."""
        self._slot = slot
        self._retry_policy = retry_policy

    @property
    def client(self) -> SqlAlchemyClient:
        """Expose the native engine owner for deliberate advanced queries."""
        return self._slot.get()

    @property
    def engine(self) -> Any:
        """Return the current SQLAlchemy async engine."""
        return self.client.engine

    @property
    def session_factory(self) -> Any:
        """Return the current SQLAlchemy async session factory."""
        return self.client.session_factory

    async def _run(self, operation: Any) -> Any:
        """Execute one transaction through the injected resilience service."""
        observed = {"generation": self._slot.generation}

        async def current_operation() -> Any:
            """Execute against and remember the active client generation."""
            observed["generation"] = self._slot.generation
            return await operation()

        return await self._retry_policy.run(
            current_operation,
            lambda: self._slot.replace(observed["generation"]),
        )

    async def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Execute and commit one textual SQL statement."""

        async def operation() -> None:
            """Commit the configured textual statement once."""
            async with self.session_factory() as session:
                await session.execute(text(sql), params)
                await session.commit()

        await self._run(operation)

    async def fetchone(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """Execute textual SQL and return one row."""

        async def operation() -> Optional[Any]:
            """Fetch one result row within a managed session."""
            async with self.session_factory() as session:
                result = await session.execute(text(sql), params)
                return result.fetchone()

        return await self._run(operation)

    async def fetchall(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        """Execute textual SQL and return all rows."""

        async def operation() -> List[Any]:
            """Fetch all result rows within a managed session."""
            async with self.session_factory() as session:
                result = await session.execute(text(sql), params)
                return list(result.fetchall())

        return await self._run(operation)

    async def run_stmt(self, stmt: "Executable", fetch: str = "all") -> Any:
        """Execute a SQLAlchemy statement and normalize the requested result."""

        async def operation() -> Any:
            """Execute and normalize one SQLAlchemy statement result."""
            async with self.session_factory() as session:
                result = await session.execute(stmt)
                if fetch == "one":
                    return result.fetchone()
                if fetch == "scalar":
                    return result.scalar()
                if fetch == "scalars":
                    return result.scalars().all()
                return result.fetchall()

        return await self._run(operation)


__all__ = ["SQLRepository"]
