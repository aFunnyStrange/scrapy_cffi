`scrapy_cffi` includes a user-friendly command-line interface (CLI) that allows you to quickly scaffold a new project or generate spiders.
While the default structure is designed to be practical out of the box, you're encouraged to adapt it to suit your own development needs.

## 1.startproject
```bash
scrapy_cffi startproject <project_name>
```

---

## 2.genspider
> After startproject <project_name>
#### 2.1 Spider
```bash
cd <project_name>
scrapy_cffi genspider <spider_name> <domain>
```

#### 2.2 RedisSpider
```bash
cd <project_name>
scrapy_cffi genspider -r <spider_name> <domain>
```

---

## 3.demo
> If you need to refer to the demo project.
#### 3.1 Normal
###### 3.1.1 Spider
```bash
scrapy_cffi demo
```

###### 3.1.2 RedisSpider
```bash
scrapy_cffi demo -r
```
## 4.extra
In real-world development, spiders are usually integrated with backend systems. `scrapy_cffi` only provides the core crawling system, while additional components such as message queues (MQ) and task schedulers (e.g., Celery) should be configured by users according to their own requirements.

**⚠️ Important Note:**
`Celery` runs as a standalone process started from the command line.
If you try to directly start a `scrapy_cffi` spider inside `Celery` code, it may lead to incorrect import paths.

**✅ Recommended Approach:**
Let the `backend` push task messages → `Celery` distributes them to specific `Redis` keys → `scrapy_cffi’s` RedisSpider consumes those keys and runs the spider accordingly.