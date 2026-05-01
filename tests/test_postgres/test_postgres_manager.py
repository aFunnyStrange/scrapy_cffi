import asyncio
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

if not importlib.util.find_spec("asyncpg"):
    print("skip: asyncpg is not installed. Install with `pip install asyncpg` or `pip install .[postgres]`.")
    sys.exit(0)

from scrapy_cffi.databases.postgres import SQLAlchemyPostgresManager


async def main():
    stop_event = asyncio.Event()
    manager = SQLAlchemyPostgresManager(
        stop_event=stop_event,
        db_url="postgresql+asyncpg://postgres:123456@127.0.0.1:5432/postgres",
    )
    await manager.init()
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
        await manager.close()


if __name__ == "__main__":
    asyncio.run(main())
