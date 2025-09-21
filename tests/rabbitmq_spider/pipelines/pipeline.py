from scrapy_cffi.databases import RedisManager
from scrapy_cffi.spiders import Spider
from scrapy_cffi.pipelines import Pipeline

class CustomPipeline1(Pipeline):
    async def open_spider(self, spider: "Spider"):
        pass

    async def process_item(self, item: dict, spider: "Spider"):
        print(f"[CustomPipeline1] Processing item: {item}")
        item["cumtom1"] = "CustomPipeline1"
        return item

    async def close_spider(self, spider: "Spider"):
        print(f"[CustomPipeline1] {spider.__class__.name} closed.")


class CustomPipeline2(Pipeline):
    async def open_spider(self, spider: "Spider"):
        pass

    async def process_item(self, item: dict, spider: "Spider"):
        print(f"[CustomPipeline2] Processing item: {item}")
        item["cumtom2"] = "CustomPipeline2"
        return item

    async def close_spider(self, spider: "Spider"):
        print(f"[CustomPipeline2] {spider.__class__.name} closed.")