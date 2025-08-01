# 1.Introduction
This pipeline follows the same behavior as Scrapy's `Item Pipeline`. It provides lifecycle hooks for spiders—such as opening and closing database connections or processing items—as part of a clean, modular design.

The decision to retain Scrapy-compatible pipeline behavior stems from the robustness and practicality of Scrapy’s original architecture. The `Item` class used in this framework is a clean and partially refactored reimplementation of Scrapy’s own `item.py` module. This ensures compatibility and familiar ergonomics for users, without requiring installation of the full Scrapy package. The design avoids reinventing the wheel while adapting it to an asyncio-based architecture.

**Item Design**
Although items behave similarly to Python dictionaries, the `Item` class provides several key advantages over raw `dict` objects:
- **Field declaration**: Fields can be explicitly declared, making data models clearer and easier to manage.
- **Validation**: Accessing or assigning undefined keys can raise errors, helping catch typos and structural issues early.
- **Extensibility**: Items support custom behavior such as serialization, nested structures, or integration with validation libraries.
- **Compatibility**: Maintaining Scrapy-style items enables familiar workflows and easy migration for users coming from Scrapy.
This framework includes a lightweight, asyncio-compatible reimplementation of Scrapy’s original `Item` logic. While raw dictionaries are still supported in pipelines and callbacks, using `Item` classes is recommended for better structure and robustness in medium to large-scale scraping projects.

# 2.Attributes
| Attribute | Description |
| --------- | ----------- |
| **settings** | The global configuration loaded from `settings.py`. |
| **logger** | A logger instance provided by the framework. |
| **redisManager** | A Redis client maintained by the framework if Redis is enabled; otherwise, this will be `None`. It includes built-in auto-retry and reconnection logic for improved reliability, and fully exposes the native Redis API—users can operate it just like a standard Redis client. |
| **hooks** | A signal hook manager that allows users to send custom signals during the pipeline lifecycle. |

# 3.Methods
# 3.1 open_spider(self, spider: "Spider")
This method is called when the spider is opened.
It is a good place to perform setup tasks such as establishing database connections to avoid reconnecting for every single item.

# 3.2 process_item(self, item: Union["Item", Dict], spider: "Spider")
Each item yielded by the spider passes through this method.
You can perform data cleaning, transformation, and persistence (e.g., saving to a database) here.

# 3.3 close_spider(self, spider: "Spider")
This method is called when the spider is closed.
It can be used to release resources, such as closing database connections.

> **Note:**
> When using the run_all_spiders mode, all spiders share a common task counter managed by the framework.
> As a result, spiders will not shut down individually after completing their own tasks, but will instead all close together after the entire task queue is processed.