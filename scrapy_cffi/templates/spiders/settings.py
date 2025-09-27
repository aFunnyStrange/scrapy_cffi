from pathlib import Path
from scrapy_cffi.utils import get_run_py_dir
from scrapy_cffi.settings import SettingsInfo

def create_settings(spider_path, env_path=None, used_redis=False, used_rabbitmq=True, used_kafka=False, *args, **kwargs):
    if env_path:
        env_file = Path(env_path)
        if env_file.exists():
            return env_to_settings(env_file, SettingsInfo)

    settings = SettingsInfo()
    settings.TIMEOUT = 30
    settings.SPIDERS_PATH = spider_path
    settings.EXTENSIONS_PATH = "extensions.CustomExtension"
    settings.ITEM_PIPELINES_PATH = ["pipelines.CustomPipeline2", "pipelines.CustomPipeline1"]
    settings.DOWNLOAD_INTERCEPTORS_PATH = {
        "interceptors.CustomDownloadInterceptor1": 300,
        "interceptors.CustomDownloadInterceptor2": 200,
    }
    settings.JS_PATH = str(get_run_py_dir() / "js_path") # can be a custom path string, or True to use the default: get_run_py_dir() / "js_path"

    # settings.DUPEFILTER = "scrapy_cffi.dupefilter.BloomDupeFilter" # In-memory Bloom filter deduplication
    # settings.DUPEFILTER = "scrapy_cffi.dupefilter.api.RedisBloomDupeFilter" # Enable Redis Bloom filter deduplication

    if used_rabbitmq:
        settings.SCHEDULER_PERSIST = True
        settings.SCHEDULER = "scrapy_cffi.scheduler.RabbitMqScheduler"
        settings.REDIS_INFO.URL = "redis://127.0.0.1:6379" # Used for request deduplication
        settings.RABBITMQ_INFO.URL = "amqp://guest:guest@localhost"
    elif used_redis:
        settings.SCHEDULER = "scrapy_cffi.scheduler.RedisScheduler" # Starting the Redis scheduler requires configuring Redis information
        settings.REDIS_INFO.URL = "redis://127.0.0.1:6379"

    if used_kafka:
        settings.KAFKA_INFO.URL = "localhost:9092"

    # settings.LOG_INFO.LOG_FILE = "demo.log"

    # Register a C extension module
    # settings.CPY_EXTENSIONS.DIR = "cpy_extensions"
    # from scrapy_cffi.models import CPYExtension
    # settings.CPY_EXTENSIONS.RESOURCES = [
    #     CPYExtension(module_name="bloom")
    # ] # Usage after injected: import bloom

    # settings.LOG_INFO.LOG_ENABLED = False # Disable logging entirely
    return settings

if __name__ == "__main__":
    from scrapy_cffi.utils import settings_to_env, env_to_settings
    from scrapy_cffi.utils import get_run_py_dir
    
    spider_path = str(get_run_py_dir() / "spiders")
    env_path = str(get_run_py_dir() / ".env.dev")

    settings: SettingsInfo = create_settings(spider_path)
    settings_to_env(settings, env_path)

    settings: SettingsInfo = env_to_settings(env_path, SettingsInfo)
    print(settings.model_dump())