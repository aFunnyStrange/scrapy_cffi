from scrapy_cffi.utils import get_run_py_dir
from scrapy_cffi.models.api import SettingsInfo

def create_settings(spider_path, user_redis=False, *args, **kwargs):
    settings = SettingsInfo()
    settings.TIMEOUT = 30
    settings.SPIDERS_PATH = spider_path
    # settings.EXTENSIONS_PATH = "extensions.CustomExtension"
    # settings.ITEM_PIPELINES_PATH = ["pipelines.CustomPipeline2", "pipelines.CustomPipeline1"]
    settings.DOWNLOAD_INTERCEPTORS_PATH = {
        # "interceptors.CustomDownloadInterceptor1": 300,
        # "interceptors.CustomDownloadInterceptor2": 200,
    }
    settings.JS_PATH = str(get_run_py_dir() / "js_path") # can be a custom path string, or True to use the default: get_run_py_dir() / "js_path"

    if user_redis:
        settings.SCHEDULER = "scrapy_cffi.scheduler.RedisScheduler" # 启动 redis 调度器需要配置 redis 信息
        settings.REDIS_INFO.REDIS_URL = "redis://127.0.0.1:6379"
    
    # settings.LOG_INFO.LOG_ENABLED = False
    return settings