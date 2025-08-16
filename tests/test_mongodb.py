import asyncio
from scrapy_cffi.databases.mongodb import MongoDBManager

async def test():
    mongo = MongoDBManager(asyncio.Event(), "mongodb://localhost:27017", "test_db")
    await mongo.init()

    await mongo.collection("test_collection").create_index("name", unique=True) # 当需要根据数据 name 进行去重时，提前配置，重复的异常需要自行捕获。不配置，mongodb允许重复数据入库
    await mongo.collection("test_collection").insert_one({"name": "Alice", "age": 23})
    await mongo.collection("test_collection").insert_one({"name": "Alice", "age": 23})

    doc = await mongo.collection("test_collection").find_one({"name": "Alice"})
    print(doc)
    print("————————————————————————————————————————")

    tables_all = mongo.collection("test_collection").find()
    async for doc in tables_all:
        print(doc)
    await mongo.drop_database("test_db")

    await mongo.close()

if __name__ == "__main__":
    asyncio.run(test())
