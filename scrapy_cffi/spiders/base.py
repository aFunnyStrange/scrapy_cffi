"""Define the framework's directly extensible spider base classes."""

import asyncio, json
from pathlib import Path
from ..core.downloader.internet.request import HttpRequest
from ..hooks import spiders_hooks
from ..settings import merge_spider_settings
from typing import Any, Callable, Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from ..core.downloader.internet.response import Response
    from ..exceptions import Failure
    from ..crawler import Crawler
    from ..hooks.spiders import SpidersHooks
    from ..settings import SettingsInfo
    from ..service import ResourceService

class BaseSpider(object):
    """Provide crawler-owned resources and overridable spider callbacks."""

    name = "cffiSpider"
    robot_scheme = "https"
    allowed_domains = []
    settings_overlay = {}  # class-level overrides merged into Crawler.settings per spider
    start_request_limit: Optional[int] = None

    def __init__(self, settings=None, run_py_dir="", stop_event=None, resources=None, session_id="", hooks=None, process_task_manager_factory=None, *args, **kwargs):
        """Bind one spider instance to crawler-owned settings and resources."""
        self.settings: "SettingsInfo" = settings
        self.run_py_dir: Path = run_py_dir
        self.stop_event: asyncio.Event = stop_event
        self.resources: "ResourceService" = resources
        self.session_id = session_id # If not set, all will share the default session
        self.hooks: "SpidersHooks" = hooks
        self._process_task_manager_factory = process_task_manager_factory
        
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
    def from_crawler(cls, crawler: "Crawler", scheduler=None):
        """Construct a spider with its scheduler-specific settings overlay."""
        sch = scheduler or crawler.scheduler
        if sch is None:
            raise RuntimeError(
                "Spider.from_crawler requires a scheduler; pass scheduler= explicitly when multiple spiders are mounted."
            )
        settings = merge_spider_settings(crawler.settings, cls)
        return cls(
            settings=settings,
            run_py_dir=crawler.run_py_dir,
            stop_event=crawler.stop_event,
            resources=crawler.resources,
            session_id="",
            hooks=spiders_hooks(crawler, sch),
            process_task_manager_factory=getattr(
                crawler,
                "get_process_task_manager",
                None,
            ),
        )

    async def run_in_process(
        self,
        func: Callable[..., Any],
        **kwargs: Any,
    ) -> Any:
        """Await one short picklable call in the crawler-owned lazy process pool."""
        if self._process_task_manager_factory is None:
            raise RuntimeError("spider is not bound to a crawler process pool")
        manager = self._process_task_manager_factory()
        return await manager.run(func, **kwargs)

    def use_execjs(self, ctx_key: str="", funcname: str="", params: tuple=()) -> str:
        """Execute one named function from a configured JavaScript context."""
        # funcName = funcname + str(params)
        funcName = f"{funcname}({','.join(json.dumps(p) for p in params)})"
        encrypt_words = self.ctx_dict[ctx_key].eval(funcName)
        return encrypt_words
    
    async def parse(self, response: "HttpResponse"):
        """Process a response in a concrete spider implementation."""
        raise NotImplementedError("parse is no defined.")

    async def resolve_client_hint(
        self,
        name: str,
        origin: str,
        response: "Response",
    ) -> Optional[str]:
        """Optionally provide a Client Hint absent from profile metadata."""
        return None

    def start_request_limit_reached(self, accepted_count: int) -> bool:
        """Return whether an ingress producer has emitted its explicit quota."""
        limit = self.start_request_limit
        return limit is not None and accepted_count >= limit
    
    async def errRet(self, failure: "Failure"):
        """Handle an unprocessed request failure."""
        print(str(failure))
        yield None

class Spider(BaseSpider):
    """Schedule configured start URLs through the standard HTTP request."""

    start_urls = []
        
    async def start(self, *args, **kwargs):
        """Yield one initial GET request for each configured start URL."""
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
