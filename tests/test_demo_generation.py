"""Verify generated crawler projects preserve supported public contracts."""

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

from scrapy_cffi.commands import demo, genspider, main as command_main, startproject


def _generate_demo(
    tmp_path: Path,
    monkeypatch,
    *,
    redis=False,
    rabbit=False,
    kafka=False,
    tls=False,
):
    """Generate one demo project with the requested queue topology flags."""
    monkeypatch.chdir(tmp_path)
    assert startproject.run("demo", is_demo=True) is None
    demo.run(redis, rabbit, kafka, use_tls=tls)
    return tmp_path / "demo"


def test_memory_demo_binds_runner_to_real_spider_class(tmp_path, monkeypatch):
    """Generate an in-memory demo with IDE-resolvable class references."""
    project = _generate_demo(tmp_path, monkeypatch)
    runner = (project / "runner.py").read_text(encoding="utf-8")
    settings = (project / "settings.py").read_text(encoding="utf-8")
    project_config = (project / "scrapy_cffi.toml").read_text(encoding="utf-8")

    assert "from spiders.customSpider import CustomSpider" in runner
    assert "DEFAULT_SPIDER: Type[BaseSpider] = CustomSpider" in runner
    assert "asyncio.WindowsSelectorEventLoopPolicy()" in runner
    assert 'spider_path="spiders.CustomSpider"' not in runner
    assert 'settings.EXTENSIONS_PATH = "' not in settings
    assert '"interceptors.CustomDownloadInterceptor' not in settings
    assert '    settings.JS_PATH = str(' not in settings
    assert "self.use_execjs(" not in (
        project / "spiders" / "customSpider.py"
    ).read_text(encoding="utf-8")
    assert 'infra_project_name = "scrapy_cffi"' in project_config


def test_tls_demo_is_standalone_and_uses_explicit_impersonate(
    tmp_path,
    monkeypatch,
):
    """Generate the CLI TLS demo without queue or Docker dependencies."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["scrapy-cffi", "demo", "-tls"],
    )

    command_main.main()

    project = tmp_path / "demo"
    spider_path = project / "spiders" / "tlsSpider.py"
    spider = spider_path.read_text(encoding="utf-8")
    runner = (project / "runner.py").read_text(encoding="utf-8")
    assert "class TlsSpider(Spider)" in spider
    assert "impersonate=impersonate" in spider
    assert 'session_id = f"tls-profile:{profile_name}"' in spider
    assert "session_id=session_id" in spider
    assert '"session_id": response.session_id' in spider
    assert '"tls_session_id": tls.get("session_id")' in spider
    assert "dont_filter=True" in spider
    assert "TLS diagnostic:" in spider
    assert "headers=self.settings.DEFAULT_HEADERS" not in spider
    assert "https://tls.peet.ws/api/all" in spider
    assert "https://tls.browserleaks.com/json" in spider
    assert "https://www.howsmyssl.com/a/check" in spider
    assert "from spiders.tlsSpider import TlsSpider" in runner
    assert "DEFAULT_SPIDER: Type[BaseSpider] = TlsSpider" in runner
    assert not (project / "infra").exists()
    assert not (project / "demo_support").exists()
    assert (project / "profiles" / "README.md").is_file()
    assert (
        project / "profiles" / "scrapy_cffi_profiles.example.toml"
    ).is_file()
    assert "scrapy-cffi demo -tls" in (
        project / "README.md"
    ).read_text(encoding="utf-8")
    assert "different profiles never share a pool" in (
        project / "README.md"
    ).read_text(encoding="utf-8")
    compile(spider, str(spider_path), "exec")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import runner; "
                "assert runner.DEFAULT_SPIDER.__name__ == 'TlsSpider'"
            ),
        ],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_redis_demo_uses_class_scheduler_and_existing_spider(tmp_path, monkeypatch):
    """Generate a Redis demo with its scheduler and local tooling."""
    project = _generate_demo(tmp_path, monkeypatch, redis=True)
    runner = (project / "runner.py").read_text(encoding="utf-8")
    settings = (project / "settings.py").read_text(encoding="utf-8")
    spider = (project / "spiders" / "customRedisSpider.py").read_text(
        encoding="utf-8"
    )

    assert "from spiders.customRedisSpider import CustomRedisSpider" in runner
    assert "DEFAULT_SPIDER: Type[BaseSpider] = CustomRedisSpider" in runner
    assert "settings.SCHEDULER = RedisScheduler" in settings
    assert "settings.SCHEDULER_LOOP_END" not in settings
    assert "SCRAPY_CFFI_DEMO_CONTINUOUS" in spider
    assert "start_request_limit = (" in spider
    assert 'data.endswith("hello: 2")' in spider
    assert "self.count" not in spider
    assert "settings.MAX_SCHEDULER_LOOP_NUM = 1" in settings
    assert '"scrapy_cffi.scheduler.RedisScheduler"' not in settings
    assert "use_redis = true" in (project / "scrapy_cffi.toml").read_text(
        encoding="utf-8"
    )
    assert (project / "scripts" / "docker-demo.bat").is_file()
    assert (project / "scripts" / "docker-demo.sh").is_file()
    assert (project / "scripts" / "demo_docker.py").is_file()
    assert (project / "infra" / "docker-compose.yml").is_file()
    assert (project / "infra" / "redis-sentinel" / "docker-compose.yml").is_file()
    assert (project / "infra" / "redis-cluster" / "docker-compose.yml").is_file()
    assert (project / "infra" / "rabbitmq-cluster" / "docker-compose.yml").is_file()
    assert (project / "infra" / "kafka-cluster" / "docker-compose.yml").is_file()
    manager = (project / "scripts" / "demo_docker.py").read_text(encoding="utf-8")
    assert '"verify-interrupt"' in manager
    assert '"infra_project_name"' in manager
    assert "signal.CTRL_BREAK_EVENT" in manager
    assert "assert_nonpersistent_cleanup(topology, log_dir)" in manager
    assert "are already in use" in manager
    assert "docker ps --filter publish=<PORT>" in manager
    assert "Only this mode's required services" in manager
    assert "signal.SIGBREAK" in runner
    assert "SCRAPY_CFFI_VERIFY_HOLD_OPEN" not in runner
    assert "SCRAPY_CFFI_DEMO_CONTINUOUS" in manager
    assert "wait_for_log_text(" in manager
    assert "continuous crawler exited without a stop event" in manager
    assert "HTTP/3 experimental request unavailable" in manager
    assert "sys.version_info >= (3, 10)" in manager
    assert "from runner import advance_main_all" in manager
    assert "await asyncio.wait_for(engine_task, timeout=60)" in manager
    assert "await asyncio.sleep(" not in manager
    assert 'DEMO_MODE = "redis"' in (
        project / "demo_support" / "topology.py"
    ).read_text(encoding="utf-8")
    if sys.platform.startswith("win"):
        batch = subprocess.run(
            ["cmd.exe", "/c", "docker-demo.bat", "plan", "sentinel"],
            cwd=str(project / "scripts"),
            capture_output=True,
            text=True,
            check=True,
        )
        assert "redis-sentinel" in batch.stdout


def test_broker_demos_keep_redis_dedup_and_default_to_cleanup(tmp_path, monkeypatch):
    """Keep Redis deduplication and cleanup in RabbitMQ and Kafka demos."""
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
        topology = (
            project / "demo_support" / "topology.py"
        ).read_text(encoding="utf-8")
        expected = "rabbitmq" if mode == "rabbit" else "kafka"
        assert 'DEMO_MODE = "%s"' % expected in topology
        requirement = (
            "scrapy_cffi[rabbitmq]"
            if mode == "rabbit"
            else "scrapy_cffi[kafka]"
        )
        requirements = (project / "requirements.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        assert requirements[0] == requirement
        assert "fastapi>=0.115" in requirements
        assert "websockets>=15.0,<16" in requirements
        assert (
            "aioquic>=1.0,<1.3; python_version < '3.10'"
            in requirements
        )
        assert (
            "aioquic>=1.3,<2; python_version >= '3.10'"
            in requirements
        )
        kafka_publisher = project / "scripts" / "push_kafka_demo.py"
        rabbit_publisher = project / "scripts" / "push_rabbitmq_demo.py"
        if mode == "kafka":
            assert kafka_publisher.is_file()
            assert not rabbit_publisher.exists()
            publisher = kafka_publisher.read_text(encoding="utf-8")
            assert "resources.kafka.push(topic" in publisher
            assert "SCRAPY_CFFI_KAFKA_BOOTSTRAP_SERVERS" in publisher
            compile(publisher, str(kafka_publisher), "exec")
            manager = (project / "scripts" / "demo_docker.py").read_text(
                encoding="utf-8"
            )
            assert '[sys.executable, "scripts/push_kafka_demo.py"]' in manager
            assert "127.0.0.1:9094,127.0.0.1:9095,127.0.0.1:9096" in manager
        else:
            assert rabbit_publisher.is_file()
            assert not kafka_publisher.exists()
        result = subprocess.run(
            [sys.executable, "scripts/demo_docker.py", "plan", "cluster"],
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
    """Generate verifier code with configurable endpoints and retained logs."""
    project = _generate_demo(tmp_path, monkeypatch)

    settings = (project / "settings.py").read_text(encoding="utf-8")
    spider = (project / "spiders" / "customSpider.py").read_text(encoding="utf-8")
    endpoints = (
        project / "demo_support" / "endpoints.py"
    ).read_text(encoding="utf-8")
    websocket_server = (
        project / "demo_support" / "server" / "ws_server.py"
    ).read_text(encoding="utf-8")
    manager = (project / "scripts" / "demo_docker.py").read_text(encoding="utf-8")
    assert "SCRAPY_CFFI_DEMO_LOG" in manager
    assert "artifacts\" / \"demo-verification" in manager
    assert "DEMO_PROCESS_URL" in spider
    assert "DEMO_WS_URL" in spider
    assert "run_in_process" in spider
    assert "PROCESS_POOL_MAX_WORKERS = 2" in settings
    assert "FFMPEG_EXECUTABLE = \"ffmpeg\"" in settings
    assert "SCRAPY_CFFI_DEMO_HTTP_PORT" in endpoints
    assert "SCRAPY_CFFI_DEMO_WS_PORT" in endpoints
    assert "SCRAPY_CFFI_DEMO_WS_PORT" in websocket_server
    assert "settings.LOG_INFO.LOG_FILE" in settings


def test_genspider_updates_runner_without_rewriting_settings_signature(
    tmp_path,
    monkeypatch,
):
    """Update the runner while preserving the generated settings API."""
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


def test_startproject_groups_application_docker_files(tmp_path, monkeypatch):
    """Keep generated deployment files grouped and expose optional settings."""
    monkeypatch.chdir(tmp_path)
    startproject.run("sample")
    project = tmp_path / "sample"

    assert (project / "docker" / "Dockerfile").is_file()
    assert (project / "docker" / "Dockerfile.dockerignore").is_file()
    compose = (project / "docker" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "context: .." in compose
    assert "dockerfile: docker/Dockerfile" in compose
    assert not (project / "Dockerfile").exists()
    assert not (project / "docker-compose.yml").exists()
    assert not (project / "__pycache__").exists()
    assert not (project / "cpy_resources").exists()
    assert (project / "profiles" / "README.md").is_file()
    assert (
        project / "profiles" / "scrapy_cffi_profiles.example.toml"
    ).is_file()
    assert (project / ".env.example").is_file()
    assert "REDIS_INFO__URL" in (
        project / ".env.example"
    ).read_text(encoding="utf-8")
    assert "settings.CURL_CFFI_RUNTIME_DIR = (" in (
        project / "settings.py"
    ).read_text(encoding="utf-8")
    assert "CURL_CFFI_RUNTIME_DIR" in (
        project / ".env.example"
    ).read_text(encoding="utf-8")
    assert not (project / "settings.example.toml").exists()


def test_demo_manager_reports_fixed_port_conflicts(tmp_path, monkeypatch):
    """Report deterministic local port conflicts before starting services."""
    project = _generate_demo(tmp_path, monkeypatch, rabbit=True)
    manager_path = project / "scripts" / "demo_docker.py"
    sys.path.insert(0, str(project))
    try:
        spec = importlib.util.spec_from_file_location(
            "generated_demo_docker",
            manager_path,
        )
        assert spec is not None and spec.loader is not None
        manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manager)
    finally:
        sys.path.remove(str(project))

    monkeypatch.setattr(
        manager,
        "port_is_available",
        lambda port: port != 6379,
    )
    monkeypatch.setattr(
        manager,
        "docker_port_owners",
        lambda port: ["existing-redis"] if port == 6379 else [],
    )

    with pytest.raises(RuntimeError) as error:
        manager.preflight_ports("single")

    message = str(error.value)
    assert "6379 (Redis): existing-redis" in message
    assert "Stop the conflicting service/container" in message
    lookup_command = "netstat -ano" if sys.platform == "win32" else "lsof -nP"
    assert lookup_command in message
