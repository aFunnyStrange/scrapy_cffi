"""Build typed crawler settings with optional operational dotenv overrides."""

from pathlib import Path
from typing import Optional, Type, Union

from extensions.extension import CustomExtension
from interceptors.interceptors import (
    CustomDownloadInterceptor1,
    CustomDownloadInterceptor2,
)
from pipelines.pipeline import CustomPipeline1, CustomPipeline2
from scrapy_cffi.scheduler import (
    KafkaScheduler,
    RabbitMqScheduler,
    RedisScheduler,
)
from scrapy_cffi.spiders import BaseSpider
from scrapy_cffi.utils.envConfig import load_env_settings
from scrapy_cffi.utils.common import get_run_py_dir
from scrapy_cffi.settings import SettingsInfo

SpiderTarget = Union[str, Path, Type[BaseSpider]]


def create_settings(
    spider_path: SpiderTarget,
    env_path: Optional[str] = None,
    used_redis: bool = False,
    used_rabbitmq: bool = False,
    used_kafka: bool = False,
    *args,
    **kwargs,
) -> SettingsInfo:
    """Assemble developer defaults and apply the project operational `.env`."""
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
    settings.EXTENSIONS_PATH = CustomExtension
    settings.ITEM_PIPELINES_PATH = [CustomPipeline2, CustomPipeline1]
    settings.DOWNLOAD_INTERCEPTORS_PATH = {
        CustomDownloadInterceptor1: 300,
        CustomDownloadInterceptor2: 200,
    }
    # Optional: requires a JavaScript runtime supported by PyExecJS.
    # settings.JS_PATH = str(get_run_py_dir() / "js_path")

    # Optional runtime-only curl adapter. Point this to an ABI-compatible
    # self-built directory containing `_wrapper`, adjacent DLL/SO files, and
    # an optional scrapy_cffi_profiles.toml alias manifest.
    # The adapter is activated only when the default curl transport is first
    # constructed; every request must still select impersonate explicitly.
    # settings.CURL_CFFI_RUNTIME_DIR = (
    #     get_run_py_dir() / "profiles" / "artifacts" / "windows-x86_64-py312"
    # )

    # Optional per-session request-start rate. None always means unlimited.
    # settings.SESSION_REQUESTS_PER_SECOND = 2.0

    # from scrapy_cffi.dupefilter import BloomDupeFilter
    # settings.DUPEFILTER = BloomDupeFilter # In-memory Bloom filter deduplication

    if used_kafka:
        settings.SCHEDULER_PERSIST = False
        settings.MAX_SCHEDULER_LOOP_NUM = 1
        settings.SCHEDULER = KafkaScheduler
        settings.REDIS_INFO.URL = "redis://127.0.0.1:6379" # Distributed deduplication (always required)
        settings.KAFKA_INFO.URL = "localhost:9092"
    elif used_rabbitmq:
        settings.SCHEDULER_PERSIST = False
        settings.SCHEDULER = RabbitMqScheduler
        settings.REDIS_INFO.URL = "redis://127.0.0.1:6379" # Distributed deduplication (always required)
        settings.RABBITMQ_INFO.URL = "amqp://guest:guest@127.0.0.1:5672"
        settings.MAX_SCHEDULER_LOOP_NUM = 1 # One crawler, run_all_spiders, aio_pika does not fully support a large number of concurrent robust connections.
    elif used_redis:
        settings.SCHEDULER = RedisScheduler # Starting the Redis scheduler requires configuring Redis information
        settings.MAX_SCHEDULER_LOOP_NUM = 1
        settings.REDIS_INFO.URL = "redis://127.0.0.1:6379"
        settings.SCHEDULER_PERSIST = False
        # Optional: shared Redis Stream consumer-group defaults for RedisSpider (spider attrs override)
        # from scrapy_cffi.config import RedisStreamConsumerInfo, RedisIngressMode
        # settings.REDIS_STREAM_INFO = RedisStreamConsumerInfo(
        #     MODE=RedisIngressMode.STREAM,
        #     STREAM_KEY="demo:stream",
        #     GROUP_NAME="demo-group",
        # )

    # settings.LOG_INFO.LOG_FILE = "demo.log"

    # Optional: scaffold custom ctypes resources with `scrapy-cffi cinstall --init <name>`.
    # from scrapy_cffi.models import CPYExtension
    # settings.CPY_EXTENSIONS.RESOURCES = [
    #     CPYExtension(module_name="custom_native")
    # ] # After load: import custom_native

    # settings.LOG_INFO.LOG_ENABLED = False # Disable logging entirely
    try:
        from demo_support.topology import apply_demo_topology
    except ImportError:
        pass
    else:
        apply_demo_topology(settings)
    project_root = get_run_py_dir()
    env_file = Path(env_path) if env_path else project_root / ".env"
    return load_env_settings(
        settings,
        env_path=env_file,
    )

if __name__ == "__main__":
    from scrapy_cffi.utils.envConfig import env_to_settings, settings_to_env
    from scrapy_cffi.utils.common import get_run_py_dir
    
    spider_path = str(get_run_py_dir() / "spiders")
    env_path = str(get_run_py_dir() / ".env.dev")

    settings: SettingsInfo = create_settings(spider_path)
    settings_to_env(settings, env_path)

    settings = env_to_settings(env_path, SettingsInfo)
    print(settings.model_dump())
