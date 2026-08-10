import asyncio
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

if not importlib.util.find_spec("asyncpg"):
    reason = (
        "asyncpg is not installed. Install with `pip install asyncpg` "
        "or `pip install .[postgres]`."
    )
    if __name__ == "__main__":
        print("skip: " + reason)
        sys.exit(0)
    import pytest

    pytest.skip(reason, allow_module_level=True)

from scrapy_cffi import build_resource_service
from scrapy_cffi.config.database import PostgresInfo
from scrapy_cffi.settings import SettingsInfo


async def main():
    stop_event = asyncio.Event()
    resources = build_resource_service(
        SettingsInfo(
            POSTGRES_INFO=PostgresInfo(
                URL="postgresql+asyncpg://postgres:123456@127.0.0.1:5432/postgres"
            )
        ),
        stop_event,
    )
    await resources.start()
    manager = resources.postgres
    if manager is None:
        raise RuntimeError("PostgreSQL repository was not configured")
    try:
        await manager.execute("drop table if exists scrapy_cffi_postgres_smoke")
        await manager.execute(
            """
            create table scrapy_cffi_postgres_smoke (
                id serial primary key,
                name text not null,
                price integer not null
            )
            """
        )
        await manager.execute(
            "insert into scrapy_cffi_postgres_smoke (name, price) values (:name, :price)",
            {"name": "demo", "price": 12},
        )
        row = await manager.fetchone(
            "select name, price from scrapy_cffi_postgres_smoke where name=:name",
            {"name": "demo"},
        )
        print(row)
    finally:
        # await manager.execute("drop table if exists scrapy_cffi_postgres_smoke")
        await resources.close()


if __name__ == "__main__":
    asyncio.run(main())
