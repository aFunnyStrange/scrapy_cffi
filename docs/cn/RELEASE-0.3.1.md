# scrapy_cffi 0.3.1：工具库解耦

[English](../en/RELEASE-0.3.1.md) | 简体中文

本版本重点支持在不加载完整爬虫栈的情况下，把 `scrapy_cffi` 当作数据库、消息队列和工具函数库独立使用。

## 主要变化

- 根包、`scrapy_cffi.utils` 与 `scrapy_cffi.tools` 按需惰性导入符号。
- 增加 `RedisManager.from_redis_info`、`*.from_db_info`、`from_rabbitmq_info` 等工厂 API。
- 增加 `settings_overlay`、`run_spiders`、`run_spiders_sync` 与多 Spider 资源归属说明。
- 媒体识别改用 `filetype` 和 `scrapy_cffi[media]`，不再区分 `[windows]`、`[unix]`。

## 快速使用

```python
from scrapy_cffi.utils.algorithm import do_sha1
from scrapy_cffi.databases import RedisManager
from scrapy_cffi.mq import RabbitMQManager

from scrapy_cffi.tools import RedisManager, canonical_request_url
```

相关文档：[独立工具](usage/13-standalone-tools.md)、[多 Spider 资源](usage/14-multi-spider-resources.md)、[架构路线图](ARCHITECTURE-ROADMAP.md)。

```bash
pip install scrapy_cffi==0.3.1
pip install "scrapy_cffi[media]"
```

下一版本：[0.3.2](RELEASE-0.3.2.md)。

