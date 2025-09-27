import asyncio
from scrapy_cffi.databases.mysql import SQLAlchemyMySQLManager
from sqlalchemy import select, Table, Column, Integer, String, MetaData
from sqlalchemy.ext.asyncio import AsyncSession

metadata = MetaData()

# Define a test table
user_table = Table(
    "test",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(50)),
)

async def test():
    # Initialize the MySQL manager
    await mysql.init()

    # 1. Create the table (run_sync is used to execute synchronous create_all)
    async with mysql.engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    # 2. Insert data
    async with mysql.session_factory() as session:
        session: AsyncSession
        await session.execute(user_table.insert().values(name="Alice"))
        await session.commit()

    # 3. Query data using run_stmt helper
    users = await mysql.run_stmt(select(user_table).where(user_table.c.name == "Alice"))
    print(users)

    # 3b. Query data directly with session
    async with mysql.session_factory() as session:
        stmt = select(user_table).where(user_table.c.name == "Alice")
        result = await session.execute(stmt)
        users = result.fetchall()
        print("查询结果：", users)

    # 4. Drop the table
    async with mysql.engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)

    # 5. Close MySQL connection
    await mysql.close()

if __name__ == "__main__":
    mysql = SQLAlchemyMySQLManager(
        stop_event=asyncio.Event(),
        host="127.0.0.1",
        port=3306,
        db="test",
        user="root",
        password="123456"
    )
    asyncio.run(test())
