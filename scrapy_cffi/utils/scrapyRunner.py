import os
import logging
from logging.handlers import TimedRotatingFileHandler
import multiprocessing
from scrapy.utils.project import get_project_settings
from scrapy.spiderloader import SpiderLoader
from scrapy.cmdline import execute

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

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    runner = ScrapyRunner()
    runner.run_all_spiders(runner.get_all_spider_names())