"""Direct-debug MySQL repository smoke flow."""

import asyncio

from sqlalchemy import Column, Integer, MetaData, String, Table, select

from scrapy_cffi import build_resource_service
from scrapy_cffi.config.database import MysqlInfo
from scrapy_cffi.settings import SettingsInfo


metadata = MetaData()
user_table = Table(
    "test",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(50)),
)


async def main() -> None:
    """Run one MySQL create, insert, query, and cleanup flow."""
    settings = SettingsInfo(
        MYSQL_INFO=MysqlInfo(
            URL="mysql+asyncmy://root:123456@127.0.0.1:3306/test"
        )
    )
    resources = build_resource_service(settings, asyncio.Event())
    await resources.start()
    mysql = resources.mysql
    if mysql is None:
        raise RuntimeError("MySQL repository was not configured")
    try:
        async with mysql.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
        async with mysql.session_factory() as session:
            await session.execute(user_table.insert().values(name="Alice"))
            await session.commit()
        rows = await mysql.run_stmt(
            select(user_table).where(user_table.c.name == "Alice")
        )
        print(rows)
        async with mysql.engine.begin() as connection:
            await connection.run_sync(metadata.drop_all)
    finally:
        await resources.close()


if __name__ == "__main__":
    asyncio.run(main())
