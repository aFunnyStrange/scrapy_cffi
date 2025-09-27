import asyncio
from scrapy_cffi.databases.mongodb import MongoDBManager

async def test():
    # Initialize MongoDBManager
    mongo = MongoDBManager(asyncio.Event(), "mongodb://localhost:27017", "test_db")
    await mongo.init()

    # Create a unique index on "name" if you want to prevent duplicates.
    # If not set, MongoDB allows duplicate entries, and insert_one may raise DuplicateKeyError if unique=True.
    await mongo.collection("test_collection").create_index("name", unique=True)

    # Insert documents
    await mongo.collection("test_collection").insert_one({"name": "Alice", "age": 23})
    await mongo.collection("test_collection").insert_one({"name": "Alice", "age": 23}) # May raise duplicate key error

    # Find one document
    doc = await mongo.collection("test_collection").find_one({"name": "Alice"})
    print(doc)
    print("————————————————————————————————————————")

    # Iterate over all documents in the collection
    tables_all = mongo.collection("test_collection").find()
    async for doc in tables_all:
        print(doc)

    # Drop the test database
    await mongo.drop_database("test_db")

    # Close the connection
    await mongo.close()

if __name__ == "__main__":
    asyncio.run(test())
