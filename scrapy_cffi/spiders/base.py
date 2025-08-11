import asyncio, json
from pathlib import Path
from ..core.downloader.internet.request import HttpRequest
from ..hooks import spiders_hooks
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..core.scheduler import RedisScheduler
    from ..core.downloader.internet.response import HttpResponse
    from ..exceptions import Failure
    from ..crawler import Crawler
    from ..hooks.spiders import SpidersHooks
    from ..models.api import SettingsInfo

class BaseSpider(object):
    name = "cffiSpider"
    robot_scheme = "https"
    allowed_domains = []

    def __init__(self, settings=None, run_py_dir="", stop_event=None, session_id="", hooks=None, *args, **kwargs):
        self.settings: "SettingsInfo" = settings
        self.run_py_dir: Path = run_py_dir
        self.stop_event: asyncio.Event = stop_event
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

class RedisSpider(BaseSpider):
    name = "redisSpider"
    redis_key = "redis_key"

    def __init__(self, 
        settings=None, 
        run_py_dir=None, 
        stop_event=None, 
        session_id="", 
        hooks=None,
        redisScheduler=None, 
        *args, **kwargs
    ):
        super().__init__(
            settings=settings, 
            run_py_dir=run_py_dir, 
            stop_event=stop_event, 
            session_id=session_id,
            hooks=hooks,
            *args, **kwargs
        )
        self.redisScheduler: "RedisScheduler" = redisScheduler

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            settings=crawler.settings,
            run_py_dir=crawler.run_py_dir,
            stop_event=crawler.stop_event,
            session_id="",
            hooks=spiders_hooks(crawler),
            redisScheduler=crawler.scheduler
        )

    async def start(self, *args, **kwargs):
        while not self.stop_event.is_set():
            get_req_task = asyncio.create_task(self.redisScheduler.get_start_req(spider=self))
            stop_task = asyncio.create_task(self.stop_event.wait())
            done, pending = await asyncio.wait(
                {get_req_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED
            )
            if stop_task in done:
                get_req_task.cancel()
                try:
                    await get_req_task
                except asyncio.CancelledError:
                    pass
                break
            if get_req_task in done:
                data = get_req_task.result()
                if not data:
                    await asyncio.sleep(1)
                    continue
                request = await self.make_request_from_data(data)
                if request:
                    yield request

    # By default, only a URL is expected. If data is in JSON format, this method should be overridden in subclasses.
    async def make_request_from_data(self, data: bytes):
        return HttpRequest(
            url=data.decode('utf-8'),
            method="GET",
            headers=self.settings.DEFAULT_HEADERS,
            cookies=self.settings.DEFAULT_COOKIES,
            proxies=self.settings.PROXIES,
            timeout=self.settings.TIMEOUT,
            dont_filter=self.settings.DONT_FILTER,
            callback=self.parse, 
            errback=self.errRet
        )