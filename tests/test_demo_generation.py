from pathlib import Path

from scrapy_cffi.commands import demo, genspider, startproject
from scripts.verify_demo import configure_e2e_project


def _generate_demo(tmp_path: Path, monkeypatch, *, redis=False, rabbit=False, kafka=False):
    monkeypatch.chdir(tmp_path)
    assert startproject.run("demo", is_demo=True) is None
    demo.run(redis, rabbit, kafka)
    return tmp_path / "demo"


def test_memory_demo_binds_runner_to_real_spider_class(tmp_path, monkeypatch):
    project = _generate_demo(tmp_path, monkeypatch)
    runner = (project / "runner.py").read_text(encoding="utf-8")
    settings = (project / "settings.py").read_text(encoding="utf-8")

    assert "from spiders.customSpider import CustomSpider" in runner
    assert "DEFAULT_SPIDER: Type[BaseSpider] = CustomSpider" in runner
    assert 'spider_path="spiders.CustomSpider"' not in runner
    assert 'settings.EXTENSIONS_PATH = "' not in settings
    assert '"interceptors.CustomDownloadInterceptor' not in settings


def test_redis_demo_uses_class_scheduler_and_existing_spider(tmp_path, monkeypatch):
    project = _generate_demo(tmp_path, monkeypatch, redis=True)
    runner = (project / "runner.py").read_text(encoding="utf-8")
    settings = (project / "settings.py").read_text(encoding="utf-8")

    assert "from spiders.customRedisSpider import CustomRedisSpider" in runner
    assert "DEFAULT_SPIDER: Type[BaseSpider] = CustomRedisSpider" in runner
    assert "settings.SCHEDULER = RedisScheduler" in settings
    assert '"scrapy_cffi.scheduler.RedisScheduler"' not in settings
    assert "use_redis = true" in (project / "scrapy_cffi.toml").read_text(
        encoding="utf-8"
    )


def test_broker_demos_keep_redis_dedup_and_default_to_cleanup(tmp_path, monkeypatch):
    for mode in ("rabbit", "kafka"):
        case = tmp_path / mode
        case.mkdir()
        project = _generate_demo(
            case,
            monkeypatch,
            rabbit=mode == "rabbit",
            kafka=mode == "kafka",
        )
        settings = (project / "settings.py").read_text(encoding="utf-8")
        assert 'settings.REDIS_INFO.URL = "redis://127.0.0.1:6379"' in settings
        assert "settings.SCHEDULER_PERSIST = False" in settings


def test_demo_verifier_injects_persistent_logs_and_isolated_servers(
    tmp_path,
    monkeypatch,
):
    project = _generate_demo(tmp_path, monkeypatch)
    log_dir = tmp_path / "evidence" / "memory"
    configure_e2e_project(
        project,
        log_dir,
        None,
        http_port=18002,
        websocket_port=18765,
    )

    settings = (project / "settings.py").read_text(encoding="utf-8")
    spider = (project / "spiders" / "customSpider.py").read_text(encoding="utf-8")
    websocket_server = (
        project / "demo_server" / "ws_server.py"
    ).read_text(encoding="utf-8")
    assert str(log_dir / "demo.log") in settings
    assert "settings.MAX_SCHEDULER_LOOP_NUM = 1" in settings
    assert "settings.SCHEDULER_LOOP_END = None" in settings
    assert "http://127.0.0.1:18002" in spider
    assert "ws://127.0.0.1:18765" in spider
    assert '"127.0.0.1", 18765' in websocket_server


def test_genspider_updates_runner_without_rewriting_settings_signature(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    startproject.run("sample")
    project = tmp_path / "sample"
    monkeypatch.chdir(project)

    genspider.run("orders", "example.com", True, False, False)

    runner = (project / "runner.py").read_text(encoding="utf-8")
    settings = (project / "settings.py").read_text(encoding="utf-8")
    assert "from spiders.orders import OrdersSpider" in runner
    assert "DEFAULT_SPIDER: Type[BaseSpider] = OrdersSpider" in runner
    assert "used_redis=True" not in settings
    assert "use_redis = true" in (project / "scrapy_cffi.toml").read_text(
        encoding="utf-8"
    )
