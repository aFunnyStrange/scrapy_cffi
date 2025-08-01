`scrapy_cffi` includes a user-friendly command-line interface (CLI) that allows you to quickly scaffold a new project or generate spiders.
While the default structure is designed to be practical out of the box, you're encouraged to adapt it to suit your own development needs.

## 1.startproject

#### 1.1 Normal
```bash
scrapy_cffi startproject <project_name>
```

#### 1.2 with tasks manager
```bash
scrapy_cffi startproject -t <project_name>
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

#### 3.2 with tasks manager
###### 3.2.1 Spider
```bash
scrapy_cffi demo -t
```

###### 3.2.2 RedisSpider
```bash
scrapy_cffi demo -t -r
```