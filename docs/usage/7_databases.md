# 1.Introduction
scrapy_cffi.databases provides adapter frameworks with automatic retry and reconnection utility classes for Redis, MySQL, and MongoDB. By default, Redis is included. For using the MySQL and MongoDB utility classes, you need to install the dependencies manually:
```bash
pip install sqlalchemy[asyncio] aiomysql
pip install motor>=3.7.1
```

# 2.Usage
`RedisManager` and `MongoDBManager` support seamless use of their native APIs. `SQLAlchemyMySQLManager` requires the use of the instance attributes `engine` and `session_factory`.

Extended usage examples for MongoDB and MySQL can be found at:
1. MongoDB: https://github.com/aFunnyStrange/scrapy_cffi/blob/main/tests/test_mongodb.py
2. MySQL: https://github.com/aFunnyStrange/scrapy_cffi/blob/main/tests/test_mysql.py
