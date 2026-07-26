from pathlib import Path
import subprocess
import sys

from scrapy_cffi.commands import demo, genspider, startproject


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
    assert (project / "docker-demo.bat").is_file()
    assert (project / "docker-demo.sh").is_file()
    assert (project / "demo_docker.py").is_file()
    assert (project / "infra" / "docker-compose.yml").is_file()
    assert (project / "infra" / "redis-sentinel" / "docker-compose.yml").is_file()
    assert (project / "infra" / "redis-cluster" / "docker-compose.yml").is_file()
    assert (project / "infra" / "rabbitmq-cluster" / "docker-compose.yml").is_file()
    assert (project / "infra" / "kafka-cluster" / "docker-compose.yml").is_file()
    manager = (project / "demo_docker.py").read_text(encoding="utf-8")
    assert '"verify-interrupt"' in manager
    assert "signal.CTRL_BREAK_EVENT" in manager
    assert "assert_nonpersistent_cleanup(topology, log_dir)" in manager
    assert "signal.SIGBREAK" in runner
    assert "SCRAPY_CFFI_VERIFY_HOLD_OPEN" in runner
    assert 'DEMO_MODE = "redis"' in (
        project / "demo_topology.py"
    ).read_text(encoding="utf-8")
    if sys.platform.startswith("win"):
        batch = subprocess.run(
            ["cmd.exe", "/c", "docker-demo.bat", "plan", "sentinel"],
            cwd=str(project),
            capture_output=True,
            text=True,
            check=True,
        )
        assert "redis-sentinel" in batch.stdout


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
        topology = (project / "demo_topology.py").read_text(encoding="utf-8")
        expected = "rabbitmq" if mode == "rabbit" else "kafka"
        assert 'DEMO_MODE = "%s"' % expected in topology
        result = subprocess.run(
            [sys.executable, "demo_docker.py", "plan", "cluster"],
            cwd=str(project),
            capture_output=True,
            text=True,
            check=True,
        )
        assert "redis-cluster" in result.stdout
        assert ("%s-cluster" % expected) in result.stdout


def test_demo_verifier_uses_environment_endpoints_and_retained_logs(
    tmp_path,
    monkeypatch,
):
    project = _generate_demo(tmp_path, monkeypatch)

    settings = (project / "settings.py").read_text(encoding="utf-8")
    spider = (project / "spiders" / "customSpider.py").read_text(encoding="utf-8")
    endpoints = (project / "demo_endpoints.py").read_text(encoding="utf-8")
    websocket_server = (
        project / "demo_server" / "ws_server.py"
    ).read_text(encoding="utf-8")
    manager = (project / "demo_docker.py").read_text(encoding="utf-8")
    assert "SCRAPY_CFFI_DEMO_LOG" in manager
    assert "artifacts\" / \"demo-verification" in manager
    assert "DEMO_HTTP_URL" in spider
    assert "DEMO_WS_URL" in spider
    assert "SCRAPY_CFFI_DEMO_HTTP_PORT" in endpoints
    assert "SCRAPY_CFFI_DEMO_WS_PORT" in endpoints
    assert "SCRAPY_CFFI_DEMO_WS_PORT" in websocket_server
    assert "settings.LOG_INFO.LOG_FILE" in settings


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
