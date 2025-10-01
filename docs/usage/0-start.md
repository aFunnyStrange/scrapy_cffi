# 1.Introduction
`scrapy_cffi` includes a user-friendly command-line interface (CLI) that allows you to quickly scaffold a new project or generate spiders.
While the default structure is designed to be practical out of the box, you're encouraged to adapt it to suit your own development needs.

**Notes:**
> The CLI command is `scrapy_cffi` in versions ≤0.1.4 and `scrapy-cffi` in versions >0.1.4 for **improved usability**.

# 2.startproject
```bash
scrapy-cffi startproject <project_name>
```

---



# 3.genspider
> After startproject <project_name>
## 3.1 Spider
```bash
cd <project_name>
scrapy-cffi genspider <spider_name> <domain>
```

## 3.2 RedisSpider
```bash
cd <project_name>
scrapy-cffi genspider -r <spider_name> <domain>
```

## 3.3 RabbitmqSpider
RabbitmqSpider has higher priority than RedisSpider. By default, it still uses Redis for deduplication.
```bash
cd <project_name>
scrapy-cffi genspider -m <spider_name> <domain>
```

---



# 4.demo
> If you need to refer to the demo project.
## 4.1 Spider
```bash
scrapy-cffi demo
```

### 4.2 RedisSpider
```bash
scrapy-cffi demo -r
```

### 4.3 RabbitmqSpider
```bash
scrapy-cffi demo -m
```


# 5.extra
In real-world development, spiders are usually integrated with backend systems. `scrapy_cffi` only provides the core crawling system, while additional components such as message queues (MQ) and task schedulers (e.g., Celery) should be configured by users according to their own requirements.

**⚠️ Important Note:**
`Celery` runs as a standalone process started from the command line.
If you try to directly start a `scrapy_cffi` spider inside `Celery` code, it may lead to incorrect import paths.

**✅ Recommended Approach:**
Let the `backend` push task messages → `Celery` distributes them to specific `Redis` keys → `scrapy_cffi’s` RedisSpider consumes those keys and runs the spider accordingly. For details, refer to [system](https://github.com/aFunnyStrange/scrapy_cffi/blob/main/docs/images/system.jpg).