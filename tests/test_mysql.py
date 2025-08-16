import asyncio
from scrapy_cffi.databases.mysql import SQLAlchemyMySQLManager
from sqlalchemy import select, Table, Column, Integer, String, MetaData
from sqlalchemy.ext.asyncio import AsyncSession

metadata = MetaData()

user_table = Table(
    "test",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(50)),
)

async def test():
    await mysql.init()

    # 1. 创建表（run_sync 用来调用同步的 create_all）
    async with mysql.engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


    # 2. 插入数据
    async with mysql.session_factory() as session:
        session: AsyncSession
        await session.execute(user_table.insert().values(name="Alice"))
        await session.commit()

    # 3. 查询数据
    users = await mysql.run_stmt(select(user_table).where(user_table.c.name == "Alice"))
    print(users)

    async with mysql.session_factory() as session:
        stmt = select(user_table).where(user_table.c.name == "Alice")
        result = await session.execute(stmt)
        users = result.fetchall()
        print("查询结果：", users)

    # 4. 删除表
    async with mysql.engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)

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
