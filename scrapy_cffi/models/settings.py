from ..models import BaseValidatedModel, StrictValidatedModel
from ..models.api import ComponentInfo, RedisInfo, MysqlInfo, MongodbInfo
from pydantic import field_validator, model_validator, ValidationInfo, PrivateAttr, Field
from typing import Optional, List, Dict, Union, Any, ClassVar, Literal

class LogInfo(StrictValidatedModel):
    _encoding_fields: ClassVar[List[str]] = ["LOG_ENCODING"]

    LOG_ENABLED: Optional[bool] = True
    LOG_WITH_STREAM: Optional[bool] = True
    LOG_LEVEL: Optional[str] = "DEBUG"
    LOG_FORMAT: Optional[str] = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    LOG_DATEFORMAT: Optional[str] = "%Y-%m-%d %H:%M:%S"
    LOG_FILE: Optional[str] = ""
    LOG_ENCODING: Optional[str] = "utf-8"
    LOG_SHORT_NAMES: Optional[bool] = False
    LOG_FORMATTER: Optional[str] = ""

    @field_validator('LOG_LEVEL')
    @classmethod
    def normalize_mute_type(cls, log_level: str):
        if log_level:
            valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
            if log_level.upper() not in valid_levels:
                raise ValueError(f'LOG_LEVEL must be one of {valid_levels}')
            return log_level.upper()
        return log_level

class SettingsInfo(BaseValidatedModel):
    # _encoding_fields: ClassVar[List[str]] = ["FEED_EXPORT_ENCODING"]

    MAX_GLOBAL_CONCURRENT_TASKS: Optional[Union[int, None]] = 300 # asyncio.BoundedSemaphore()
    PROJECT_NAME: Optional[Union[str]] = "" # # If set, this queue will be shared in run_all_spiders mode. Be aware of potential request race conditions when using the same scheduler.
    ROBOTSTXT_OBEY: Optional[bool] = True # Whether to respect robots.txt rules

    USER_AGENT: Optional[str] = "scrapy_cffiBot"
    DEFAULT_HEADERS: Optional[Dict] = Field(default_factory=dict)
    DEFAULT_COOKIES: Optional[Dict] = Field(default_factory=dict)
    MAX_CONCURRENT_REQ: Optional[int] = None # asyncio.Semaphore()
    USE_STRICT_SEMAPHORE: Optional[bool] = False # asyncio.BoundedSemaphore()
    TIMEOUT: Optional[int] = 30 # Request timeout in seconds
    MAX_REQ_TIMES: Optional[int] = 2 # Maximum number of retry attempts for a failed request
    DELAY_REQ_TIME: Optional[int] = 3 # Delay in seconds before retrying a failed request
    
    PROXY_URL: Optional[str] = None
    PROXIES: Optional[Dict] = None
    PROXIES_LIST: Optional[List[str]] = Field(default_factory=list)
    
    SPIDERS_PATH: Optional[str] = None # If not set, defaults to the `spiders` directory under the current running script
    SPIDER_INTERCEPTORS_PATH: Optional[Union[ComponentInfo, Dict[str, int], List[str], str, None]] = ComponentInfo()
    DOWNLOAD_INTERCEPTORS_PATH: Optional[Union[ComponentInfo, Dict[str, int], List[str], str, None]] = ComponentInfo()
    ITEM_PIPELINES_PATH: Optional[Union[ComponentInfo, Dict[str, int], List[str], str, None]] = ComponentInfo()
    EXTENSIONS_PATH: Optional[Union[ComponentInfo, Dict[str, int], List[str], str, None]] = ComponentInfo()

    SCHEDULER: Optional[str] = None
    SCHEDULER_PERSIST: Optional[bool] = False
    INCLUDE_HEADERS: Optional[List] = Field(default_factory=list) # Keys in headers to include during deduplication
    FILTER_KEY: Optional[str] = "cffiFilter"
    DONT_FILTER: Optional[bool] = False
    _filter_new_seen_req_key: str = PrivateAttr()
    _filter_is_req_key: str = PrivateAttr()

    WS_END_TAG: Optional[str] = "websocket end" # You can customize the TAG to avoid conflicts with the response content
    RET_COOKIES: Optional[Union[str, Literal[False]]] = "ret_cookies"  # False to disable cookie return; a string to specify the key used for returned cookies
    
    JS_PATH: Optional[Union[str, bool]] = None # Absolute/relative path to JS files or default to ./js_path under the running script directory
    REDIS_INFO: Optional[RedisInfo] = RedisInfo()
    MYSQL_INFO: Optional[MysqlInfo] = MysqlInfo()
    MONBODB_INFO: Optional[MongodbInfo] = MongodbInfo()
    LOG_INFO: Optional[LogInfo] = LogInfo()
    
    @property
    def _FILTER_NEW_SEEN_REQ_KEY(self):
        return self._filter_new_seen_req_key
    
    @property
    def _FILTER_IS_REQ_KEY(self):
        return self._filter_is_req_key

    # Used to warn users about custom fields not recognized by the framework; these should be maintained by the user
    def __init__(self, **data: Any):
        super().__init__(**data)
        known_fields = set(self.model_fields.keys())
        extra_fields = set(data.keys()) - known_fields
        if extra_fields:
            import warnings
            warnings.warn(
                f"SettingsInfo received unrecognized fields: {extra_fields}. "
                "These fields will be ignored by the framework internals and should be managed by user code."
            )

    # Strict validation for component types
    @field_validator(
        "SPIDER_INTERCEPTORS_PATH",
        "DOWNLOAD_INTERCEPTORS_PATH",
        "ITEM_PIPELINES_PATH",
        "EXTENSIONS_PATH",
        mode="before"
    )
    @classmethod
    def validate_component(cls, v, info: ValidationInfo):
        if v is None or isinstance(v, ComponentInfo):
            return v
        return ComponentInfo.from_raw(v, info.field_name)
    
    @model_validator(mode='after')
    def check_after(self):
        if self.PROXY_URL:
            self.PROXIES = {"http": self.PROXY_URL, "https": self.PROXY_URL}

        self._filter_new_seen_req_key  = f'{self.FILTER_KEY}_new_seen_req_key'
        self._filter_is_req_key = f'{self.FILTER_KEY}_is_req_key'
        return self
    
__all__ = [
    "LogInfo",
    "SettingsInfo"
]