import asyncio, json
from pathlib import Path
from ..core.downloader.internet.request import HttpRequest
from ..hooks import spiders_hooks
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..core.downloader.internet.response import HttpResponse
    from ..exceptions import Failure
    from ..crawler import Crawler
    from ..hooks.spiders import SpidersHooks
    from ..settings import SettingsInfo
    from ..mq.kafka import KafkaManager

class BaseSpider(object):
    name = "cffiSpider"
    robot_scheme = "https"
    allowed_domains = []

    def __init__(self, settings=None, run_py_dir="", stop_event=None, kafkaManager=None, session_id="", hooks=None, *args, **kwargs):
        self.settings: "SettingsInfo" = settings
        self.run_py_dir: Path = run_py_dir
        self.stop_event: asyncio.Event = stop_event
        self.kafkaManager: "KafkaManager" = kafkaManager
        self.session_id = session_id # If not set, all will share the default session
        self.hooks: "SpidersHooks" = hooks
        
        # Whether to load the JS method; place it under the project's root js_path
        self.ctx_dict = {}
        if self.settings.JS_PATH:
            import execjs, os
            if isinstance(self.settings.JS_PATH, str):
                js_path = Path(self.settings.JS_PATH)
            else:
                js_path = self.run_py_dir / "js_path"
            js_files = os.listdir(js_path)
            for js_file in js_files:
                single_js_file_path = js_path / js_file
                self.ctx_dict["".join(js_file.split(".")[:-1])] = execjs.compile(open(single_js_file_path, encoding='utf-8').read())

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            settings=crawler.settings,
            run_py_dir=crawler.run_py_dir,
            stop_event=crawler.stop_event,
            kafkaManager=crawler.kafkaManager,
            session_id="",
            hooks=spiders_hooks(crawler),
        )

    def use_execjs(self, ctx_key: str="", funcname: str="", params: tuple=()) -> str:
        # funcName = funcname + str(params)
        funcName = f"{funcname}({','.join(json.dumps(p) for p in params)})"
        encrypt_words = self.ctx_dict[ctx_key].eval(funcName)
        return encrypt_words
    
    async def parse(self, response: "HttpResponse"):
        raise NotImplementedError("parse is no defined.")
    
    async def errRet(self, failure: "Failure"):
        print(str(failure))
        yield None

class Spider(BaseSpider):
    start_urls = []
        
    async def start(self, *args, **kwargs):
        for url in self.start_urls:
            yield HttpRequest(
                session_id=self.session_id,
                url=url,
                method="GET",
                headers=self.settings.DEFAULT_HEADERS,
                cookies=self.settings.DEFAULT_COOKIES,
                proxies=self.settings.PROXIES,
                timeout=self.settings.TIMEOUT,
                dont_filter=self.settings.DONT_FILTER,
                callback=self.parse, 
                errback=self.errRet,
            )