1.start all server in dir "demo_server"
2.run test_rabbitmq.py
3.redis-cli
4.del cffiFilter_new_seen
5.del cffiFilter_sent_seen
6.run runner.py

different from redisSpider:

settings.py
settings.SCHEDULER = "scrapy_cffi.scheduler.RabbitMqScheduler"
settings.REDIS_INFO.URL = "redis://127.0.0.1:6379"
settings.RABBITMQ_INFO.URL = "amqp://guest:guest@localhost"

spider.py (base_class and attr change)
from scrapy_cffi.spiders.rabbitmq import RabbitmqSpider

class CustomRedisSpider(RabbitmqSpider):
    rabbitmq_queue = "scrapy_cffi"