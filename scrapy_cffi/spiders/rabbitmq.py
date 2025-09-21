from .redis import RedisSpider

class RabbitmqSpider(RedisSpider):
    name = "rabbitmqSpider"
    rabbitmq_queue = "scrapy_cffi"