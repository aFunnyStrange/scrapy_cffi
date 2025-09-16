import os
import multiprocessing, threading
try:
    from scrapy.utils.project import get_project_settings
    from scrapy.spiderloader import SpiderLoader
    from scrapy.cmdline import execute
    from twisted.internet import reactor
    from scrapy.crawler import CrawlerRunner
    from scrapy.utils.log import configure_logging
except ImportError as e:
    raise ImportError(
        "Missing scrapy dependencies. "
        "Please install: pip install scrapy"
    ) from e

from typing import List, TYPE_CHECKING
if TYPE_CHECKING:
    from scrapy.settings import Settings

class ScrapyRunner:
    def __init__(self):
        self.settings = get_project_settings()

    def get_all_spider_names(self) -> List[str]:
        spider_loader = SpiderLoader.from_settings(self.settings)
        spiders = spider_loader.list()
        print(f"There are {len(spiders)} spiders: {spiders}")
        return spiders

    def run_all_spiders(self, spiders: List[str]=None) -> None:
        spiders = spiders or self.get_all_spider_names()
        for spider_name in spiders:
            p = multiprocessing.Process(target=self.run_spider, args=(spider_name,), daemon=True)
            p.start()
            print(f"Start spider：{spider_name}，pid={p.pid}")

    def run_spider(self, spider_name: str) -> None:
        os.environ.setdefault('SCRAPY_SETTINGS_MODULE', 'ins_collect.settings')
        execute(["scrapy", "crawl", spider_name])

def run_spider_in_process(settings: "Settings", spider_name: str) -> None:
    runner = CrawlerRunner(settings)
    d = runner.crawl(spider_name)
    d.addBoth(lambda _: reactor.stop())
    reactor.run()

class InlineScrapyRunner:
    """Run Scrapy spiders in the current process in a non-blocking way using CrawlerRunner."""

    def __init__(self, settings_module: str = "myproject.settings"):
        os.environ.setdefault("SCRAPY_SETTINGS_MODULE", settings_module)
        self.settings: "Settings" = get_project_settings()
        configure_logging()
        self.runner = CrawlerRunner(self.settings)

    def get_all_spider_names(self) -> List[str]:
        spider_loader = SpiderLoader.from_settings(self.settings)
        spiders = spider_loader.list()
        print(f"There are {len(spiders)} spiders: {spiders}")
        return spiders
    
    def run_all_spiders(self, spiders: List[str]=None, use_process: bool = True) -> None:
        spiders = spiders or self.get_all_spider_names()
        for spider_name in spiders:
            self.run_spider(spider_name=spider_name, use_process=use_process)

    def run_spider(self, spider_name: str, use_process: bool = True) -> None:
        if use_process:
            p = multiprocessing.Process(
                target=run_spider_in_process,
                args=(self.settings, spider_name),
                daemon=True
            )
            p.start()
            print(f"[Process mode] Start spider {spider_name}, pid={p.pid}")
        else:
            self.runner.crawl(spider_name)
            if not reactor.running:
                threading.Thread(
                    target=reactor.run,
                    kwargs={"installSignalHandlers": False},
                    daemon=True
                ).start()

__all__ = [
    "ScrapyRunner",
    "InlineScrapyRunner"
]

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    runner = ScrapyRunner()
    runner.run_all_spiders(runner.get_all_spider_names())