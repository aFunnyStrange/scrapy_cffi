import sys
from pathlib import Path
from scrapy_cffi.utils import get_run_py_dir
from scrapy_cffi.settings import SettingsInfo

def create_settings(spider_path, env_path=None, used_redis=False, used_rabbitmq=False, used_kafka=False, *args, **kwargs):
    if env_path:
        env_file = Path(env_path)
        if env_file.exists():
            return env_to_settings(env_file, SettingsInfo)

    # Optional flags from scrapy_cffi.toml (written by `scrapy-cffi demo -r/-m/-k`)
    try:
        import toml
        cfg_path = get_run_py_dir() / "scrapy_cffi.toml"
        if cfg_path.exists():
            cfg = toml.load(cfg_path)
            d = cfg.get("default") or {}
            if "use_redis" in d:
                used_redis = bool(d["use_redis"])
            if "use_rabbitmq" in d:
                used_rabbitmq = bool(d["use_rabbitmq"])
            if "use_kafka" in d:
                used_kafka = bool(d["use_kafka"])
    except Exception:
        pass

    settings = SettingsInfo()
    settings.ROBOTSTXT_OBEY = False  # Demo server randomizes robots.txt and can introduce noisy nondeterminism.
    settings.TIMEOUT = 30
    settings.SPIDERS_PATH = spider_path
    settings.EXTENSIONS_PATH = "extensions.CustomExtension"
    settings.ITEM_PIPELINES_PATH = ["pipelines.CustomPipeline2", "pipelines.CustomPipeline1"]
    settings.DOWNLOAD_INTERCEPTORS_PATH = {
        "interceptors.CustomDownloadInterceptor1": 300,
        "interceptors.CustomDownloadInterceptor2": 200,
    }
    settings.JS_PATH = str(get_run_py_dir() / "js_path") # can be a custom path string, or True to use the default: get_run_py_dir() / "js_path"

    if sys.platform.startswith("win"):
        # Keep bounded defaults for run_all_spiders stability on Windows.
        settings.MAX_GLOBAL_CONCURRENT_TASKS = 200
        settings.MAX_CONCURRENT_REQ = 50

    # settings.DUPEFILTER = "scrapy_cffi.dupefilter.BloomDupeFilter" # In-memory Bloom filter deduplication
    # settings.DUPEFILTER = "scrapy_cffi.dupefilter.api.RedisBloomDupeFilter" # Enable Redis Bloom filter deduplication

    if used_rabbitmq:
        settings.SCHEDULER_PERSIST = True
        settings.SCHEDULER = "scrapy_cffi.scheduler.RabbitMqScheduler"
        settings.REDIS_INFO.URL = "redis://127.0.0.1:6379" # Used for request deduplication
        settings.RABBITMQ_INFO.URL = "amqp://guest:guest@127.0.0.1:5672"
        # settings.SCHEDULER_LOOP_END = 5
        settings.MAX_SCHEDULER_LOOP_NUM = 1 # One crawler, run_all_spiders, aio_pika does not fully support a large number of concurrent robust connections.
    elif used_redis:
        settings.SCHEDULER = "scrapy_cffi.scheduler.RedisScheduler" # Starting the Redis scheduler requires configuring Redis information
        settings.REDIS_INFO.URL = "redis://127.0.0.1:6379"
        # Optional: shared Redis Stream consumer-group defaults for RedisSpider (spider attrs override)
        # from scrapy_cffi.models import RedisStreamConsumerInfo, RedisIngressMode
        # settings.REDIS_STREAM_INFO = RedisStreamConsumerInfo(
        #     MODE=RedisIngressMode.STREAM,
        #     STREAM_KEY="demo:stream",
        #     GROUP_NAME="demo-group",
        # )
        # settings.SCHEDULER_LOOP_END = 5

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
    from scrapy_cffi.utils.envConfig import settings_to_env, env_to_settings
    from scrapy_cffi.utils import get_run_py_dir
    
    spider_path = str(get_run_py_dir() / "spiders")
    env_path = str(get_run_py_dir() / ".env.dev")

    settings: SettingsInfo = create_settings(spider_path)
    settings_to_env(settings, env_path)

    settings: SettingsInfo = env_to_settings(env_path, SettingsInfo)
    print(settings.model_dump())