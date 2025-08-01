import asyncio, random, logging
from urllib.parse import urlparse
from typing import Union, AsyncGenerator
from collections.abc import AsyncIterable, Iterable
from .base import _InnerSpiderInterceptor
from ..spiders import Spider
from ..hooks import interceptors_hooks
from ..core.downloader.internet import *
from ..exceptions import SessionEndError, BlockRequestError, FilterDomainRequestError
from typing import TYPE_CHECKING, Dict
if TYPE_CHECKING:
    from ..crawler import Crawler
    from ..models.api import SettingsInfo
    from ..utils import RobotsManager
    from ..item import Item
    from ..hooks.interceptors import InterceptorsHooks
    from ..core.sessions import  SessionWrapper, WebSocketEntry

class UpdateRequestSpiderInterceptor(_InnerSpiderInterceptor):
    ResultType = Union[
        AsyncGenerator,
        AsyncIterable,
        Iterable,
        Request,
        Dict,
        None,
    ]

    def __init__(
        self, 
        stop_event: asyncio.Event=None, 
        settings: "SettingsInfo"=None, 
        hooks: "InterceptorsHooks"=None, 
        sessions_lock=None,
        **kwargs
    ):
        super().__init__(stop_event=stop_event, settings=settings, hooks=hooks, sessions_lock=sessions_lock, **kwargs)
        self.logger: logging.Logger = logging.getLogger(__name__)

        self.default_ua = self.settings.USER_AGENT
        self.default_headers = self.settings.DEFAULT_HEADERS
        self.timeout = self.settings.TIMEOUT
        self.dont_filter = self.settings.DONT_FILTER
        self.proxies = self.settings.PROXIES
        self.proxies_list = self.settings.PROXIES_LIST
        self.proxies_list = [{"http": proxy_url, "https": proxy_url} for proxy_url in self.settings.PROXIES_LIST]

    def pre_check(self, request: Request) -> Request:
        if not request.headers:
            request.headers = self.default_headers
        if self.default_ua:
            ua = request.find_header_key(key="user-agent")
            if not ua:
                request.headers["user-agent"] = self.default_ua

        if not request.timeout:
            request.timeout = self.timeout

        if request.no_proxy:
            request.proxies = None
        elif not request.proxies:
            if self.proxies:
                request.proxies = self.proxies
            elif self.proxies_list:
                request.proxies = random.choice(self.proxies_list)

        if request.dont_filter is None:
            request.dont_filter = True if self.dont_filter else False
        return request

    async def process_spider_output(self, response: Response, result: ResultType, spider: Spider):
        """
        Default Spider Middleware

        This middleware is the first in the spider middleware chain and serves as a foundational processor for all requests.

        Key responsibilities:
        - Complete and validate all requests before further processing.
        - Manage concurrency by locking sessions to prevent race conditions.
        - Ensure WebSocket requests correctly associate with existing WebSocket connections,
        handling session cookie updates and URL assignments.
        - Detect and handle closed WebSocket connections gracefully by returning errors and logging warnings.

        This middleware ensures that subsequent middleware and the engine receive well-formed,
        locked, and valid requests, especially important for managing WebSocket sessions.

        It plays a critical role in stabilizing the request lifecycle and maintaining session consistency.
        """
        if isinstance(result, Request):
            async with self.sessions_lock:
                self.hooks.session.acquire(session_id=result.session_id)

                result = self.pre_check(result)
                wrapper: "SessionWrapper" = self.hooks.session.get_or_create_session(session_id=result.session_id, cookies=result.cookies)
                if result.cookies:
                    wrapper.update_session_cookies(cookies_dict=result.cookies)

                # For non-initial WebSocket requests:
                # The websocket_pool should already contain the key, 
                # so ensure the request.url is set accordingly and acquire a lock on it.
                # For initial WebSocket requests, only the session lock is applied.
                if isinstance(result, WebSocketRequest) and ((not result.url) and result.websocket_id):
                    webSocket_entry: "WebSocketEntry" = wrapper.websocket_pool.get_from_key(result.websocket_id)
                    if webSocket_entry:
                        result.url = webSocket_entry.url
                        wrapper.websocket_pool.acquire_from_url(url=result.url)
                    else:
                        error_text = f'WebSocket connection {result.websocket_id} has been closed, but a new WebSocketRequest was received.'
                        self.logger.warning(f'WebSocket connection {result.websocket_id} has been closed, but a new WebSocketRequest was received: {result.send_message.decode()}')
                        return SessionEndError(exception=ValueError(error_text), request=result)
        return result
    
class RobotSpiderInterceptor(_InnerSpiderInterceptor):
    def __init__(
        self,  
        stop_event: asyncio.Event=None, 
        settings: "SettingsInfo"=None, 
        hooks: "InterceptorsHooks"=None, 
        sessions_lock=None, 
        robot: "RobotsManager"=None,
        **kwargs
    ):
        super().__init__(stop_event=stop_event, settings=settings, hooks=hooks, sessions_lock=sessions_lock, **kwargs)
        self.robot = robot
        from ..utils import init_logger
        self.logger = init_logger(log_info=self.settings.LOG_INFO, logger_name=__name__)

    @classmethod
    def from_crawler(cls, crawler: "Crawler"):
        return cls(
            stop_event=crawler.stop_event,
            settings=crawler.settings,
            hooks=interceptors_hooks(crawler),
            sessions_lock=crawler.sessions_lock,
            robot=crawler.robot
        )

    def is_allow(self, url, allow_domains):
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            return False
        domain = domain.lower()
        for allowed in allow_domains:
            allowed = allowed.lower()
            if domain == allowed or domain.endswith('.' + allowed):
                return True
        return False

    async def process_spider_output(self, response: Response, result: Union[Request, "Item", dict, None], spider: Spider):
        """
        Default second spider middleware.

        Responsibilities:
        - Filter out requests whose URLs are not within the spider's allowed domains.
        - Release the session lock for filtered requests.
        - Enforce robots.txt rules if enabled in settings.
        - Log warnings or debug messages when requests are filtered or blocked.
        - Return specific exceptions to indicate filtered or blocked requests.

        Parameters:
        - response: The HTTP response associated with the spider output.
        - result: The spider output item, typically a Request, Item, dict, or None.
        - spider: The spider instance.

        Returns:
        - The original result if allowed.
        - An error wrapper object if the request is filtered or blocked.
        """
        if isinstance(result, Request) and result.url:
            is_start_url = result.meta.pop("is_start_url", None)
            if not is_start_url:
                is_allow_res = self.is_allow(url=result.url, allow_domains=spider.allowed_domains)
                if not is_allow_res:
                    async with self.sessions_lock:
                        self.hooks.session.release(session_id=result.session_id)
                    log_text = f"Request URL {result.url} is outside allowed_domains and has been filtered"
                    self.logger.warning(log_text)
                    return FilterDomainRequestError(exception=ValueError(log_text), request=result)
                
                if self.settings.ROBOTSTXT_OBEY and (not self.robot.is_allowed(result.url)):
                    async with self.sessions_lock:
                        self.hooks.session.release(session_id=result.session_id)
                    log_text = f"[robots.txt] Blocked: {result.url}"
                    self.logger.debug(log_text)
                    return BlockRequestError(exception=ValueError(log_text), request=result)
        return result