import os
import logging
from logging.handlers import TimedRotatingFileHandler
import multiprocessing, threading
try:
    from scrapy.utils.project import get_project_settings
    from scrapy.spiderloader import SpiderLoader
    from scrapy.cmdline import execute
    from twisted.internet import reactor
    from scrapy.crawler import CrawlerRunner
    from scrapy.utils.project import get_project_settings
    from scrapy.spiderloader import SpiderLoader
    from scrapy.utils.log import configure_logging
except ImportError as e:
    raise ImportError(
        "Missing scrapy dependencies. "
        "Please install: pip install scrapy"
    ) from e

class ScrapyRunner:
    def __init__(self):
        self.settings = get_project_settings()

    def get_all_spider_names(self):
        spider_loader = SpiderLoader.from_settings(self.settings)
        spiders = spider_loader.list()
        print(f"There are {len(spiders)} spiders: {spiders}")
        return spiders

    def run_all_spiders(self, spiders):
        for spider_name in spiders:
            p = multiprocessing.Process(target=self.run_spider, args=(spider_name,), daemon=True)
            p.start()
            print(f"Start spider：{spider_name}，pid={p.pid}")

    def run_spider(self, spider_name):
        os.environ.setdefault('SCRAPY_SETTINGS_MODULE', 'ins_collect.settings')

        log_dir = os.path.join(os.getcwd(), "scrapy_logs", spider_name)
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, f"{spider_name}.log")

        # close when debug
        # sys.stdout = open(log_file_path, 'a', encoding='utf-8')
        # sys.stderr = open(log_file_path, 'a', encoding='utf-8')

        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        handler = TimedRotatingFileHandler(
            filename=log_file_path,
            when='D',
            interval=1,
            backupCount=15,
            encoding='utf-8'
        )
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        handler.setFormatter(formatter)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
        logger.addHandler(handler)
        execute(["scrapy", "crawl", spider_name])

class InlineScrapyRunner:
    """Run Scrapy spiders in the current process in a non-blocking way using CrawlerRunner."""

    def __init__(self, settings_module: str = "myproject.settings"):
        os.environ.setdefault("SCRAPY_SETTINGS_MODULE", settings_module)
        self.settings = get_project_settings()
        configure_logging()
        self.runner = CrawlerRunner(self.settings)

    def get_all_spider_names(self):
        spider_loader = SpiderLoader.from_settings(self.settings)
        return spider_loader.list()

    def run_all_spiders(self, spiders=None):
        spiders = spiders or self.get_all_spider_names()
        for spider_name in spiders:
            self.runner.crawl(spider_name)
        # Start reactor in a separate thread so it doesn't block
        threading.Thread(target=reactor.run, kwargs={"installSignalHandlers": False}, daemon=True).start()

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    runner = ScrapyRunner()
    runner.run_all_spiders(runner.get_all_spider_names())