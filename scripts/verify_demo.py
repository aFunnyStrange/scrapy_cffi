"""One-command, serial verification for every scrapy-cffi demo transport.

This is a framework-maintainer check. It creates disposable demo projects,
starts only the required local Docker infrastructure for each case, runs the
generated-project and scheduler/broker checks, then removes the containers and
volumes before continuing.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, IO, Iterator, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PROJECT = "scrapy_cffi_demo_verify"


@contextmanager
def working_directory(path: Path) -> Iterator[None]:
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def run(
    command: List[str],
    *,
    cwd: Path = ROOT,
    env: Optional[Dict[str, str]] = None,
    output_path: Optional[Path] = None,
) -> None:
    print(f"\n>>> {' '.join(command)}", flush=True)
    if output_path is None:
        subprocess.run(command, cwd=str(cwd), env=env, check=True)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=True,
        )


def generate_demo(case_dir: Path, flag: str) -> Path:
    from scrapy_cffi.commands import demo, startproject

    case_dir.mkdir(parents=True)
    with working_directory(case_dir):
        if startproject.run("demo", is_demo=True) is not None:
            raise RuntimeError("Failed to create disposable demo project")
        demo.run(flag == "-r", flag == "-m", flag == "-k")
    return case_dir / "demo"


def verify_generated_project(project: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), str(project), env.get("PYTHONPATH", "")]
    )
    run(
        [
            sys.executable,
            "-c",
            (
                "import compileall, runner, settings; "
                "assert compileall.compile_dir('.', quiet=1); "
                "assert runner.DEFAULT_SPIDER is not None; "
                "settings.create_settings(runner.DEFAULT_SPIDER)"
            ),
        ],
        cwd=project,
        env=env,
    )


def project_environment(
    project: Path,
    broker_environment: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    env = dict(broker_environment or os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), str(project), env.get("PYTHONPATH", "")]
    )
    env["PYTHONUNBUFFERED"] = "1"
    return env


def configure_e2e_project(
    project: Path,
    log_dir: Path,
    broker_environment: Optional[Dict[str, str]],
    http_port: int,
    websocket_port: int,
) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    settings_path = project / "settings.py"
    settings_text = settings_path.read_text(encoding="utf-8")
    environment = broker_environment or {}
    replacements = {
        "redis://127.0.0.1:6379": environment.get(
            "SCRAPY_CFFI_REDIS_URL",
            "redis://127.0.0.1:6379/0",
        ),
        "amqp://guest:guest@127.0.0.1:5672": environment.get(
            "SCRAPY_CFFI_AMQP_URL",
            "amqp://guest:guest@127.0.0.1:5672/",
        ),
        "localhost:9092": environment.get(
            "SCRAPY_CFFI_KAFKA",
            "127.0.0.1:9092",
        ),
    }
    for old, new in replacements.items():
        settings_text = settings_text.replace(old, new)
    marker = '    # settings.LOG_INFO.LOG_FILE = "demo.log"'
    if marker not in settings_text:
        raise RuntimeError("Generated settings log marker was not found")
    settings_text = settings_text.replace(
        marker,
        (
            f"    settings.LOG_INFO.LOG_FILE = {str(log_dir / 'demo.log')!r}\n"
            "    settings.MAX_SCHEDULER_LOOP_NUM = 1\n"
            "    settings.SCHEDULER_LOOP_END = None"
        ),
    )
    settings_path.write_text(settings_text, encoding="utf-8")

    for spider_path in (project / "spiders").glob("*.py"):
        spider_text = spider_path.read_text(encoding="utf-8")
        spider_text = spider_text.replace(
            "http://127.0.0.1:8002",
            f"http://127.0.0.1:{http_port}",
        )
        spider_text = spider_text.replace(
            "ws://localhost:8765",
            f"ws://127.0.0.1:{websocket_port}",
        )
        spider_path.write_text(spider_text, encoding="utf-8")

    ws_path = project / "demo_server" / "ws_server.py"
    ws_text = ws_path.read_text(encoding="utf-8")
    ws_text = ws_text.replace(
        'websockets.serve(handle_connection, "localhost", 8765)',
        (
            "websockets.serve("
            f'handle_connection, "127.0.0.1", {websocket_port}'
            ")"
        ),
    )
    ws_path.write_text(ws_text, encoding="utf-8")


def wait_for_http(port: int, process: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"HTTP demo server exited early: {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except BaseException:
            time.sleep(0.1)
    raise TimeoutError(f"HTTP demo server did not become ready: {url}")


def wait_for_websocket(
    port: int,
    process: subprocess.Popen,
    timeout: float = 20.0,
) -> None:
    import websockets

    async def probe() -> None:
        async with websockets.connect(f"ws://127.0.0.1:{port}/"):
            pass

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"WebSocket demo server exited early: {process.returncode}"
            )
        try:
            asyncio.run(probe())
            return
        except BaseException:
            time.sleep(0.1)
    raise TimeoutError(f"WebSocket demo server did not become ready on port {port}")


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def start_demo_servers(
    project: Path,
    log_dir: Path,
    http_port: int,
    websocket_port: int,
) -> Tuple[List[subprocess.Popen], List[IO]]:
    server_dir = project / "demo_server"
    handles: List[IO] = [
        (log_dir / "http_server.log").open("w", encoding="utf-8"),
        (log_dir / "websocket_server.log").open("w", encoding="utf-8"),
    ]
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "uvicorn",
                "fastApiServer:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(http_port),
            ],
            cwd=str(server_dir),
            stdout=handles[0],
            stderr=subprocess.STDOUT,
        ),
        subprocess.Popen(
            [sys.executable, "-u", "ws_server.py"],
            cwd=str(server_dir),
            stdout=handles[1],
            stderr=subprocess.STDOUT,
        ),
    ]
    try:
        wait_for_http(http_port, processes[0])
        wait_for_websocket(websocket_port, processes[1])
    except BaseException:
        for process in processes:
            stop_process(process)
        for handle in handles:
            handle.close()
        raise
    return processes, handles


def enqueue_start_request(
    name: str,
    project: Path,
    environment: Dict[str, str],
    start_url: str,
    log_dir: Path,
) -> None:
    if name == "memory":
        return
    if name == "redis":
        code = (
            "import asyncio, os\n"
            "from redis.asyncio import from_url\n"
            "async def main():\n"
            "    redis = from_url(os.environ['SCRAPY_CFFI_REDIS_URL'])\n"
            f"    await redis.rpush('customRedisSpider_test', {start_url!r})\n"
            "    await redis.aclose()\n"
            "asyncio.run(main())\n"
        )
    elif name == "rabbitmq":
        code = (
            "import asyncio, os\n"
            "from scrapy_cffi.mq.rabbitmq import RabbitMQManager\n"
            "async def main():\n"
            "    manager = RabbitMQManager(\n"
            "        asyncio.Event(), os.environ['SCRAPY_CFFI_AMQP_URL'], persist=False\n"
            "    )\n"
            f"    await manager.rpush('scrapy_cffi', {start_url.encode()!r})\n"
            "    await manager.close()\n"
            "asyncio.run(main())\n"
        )
    else:
        code = (
            "import asyncio, os\n"
            "from scrapy_cffi.mq.kafka import KafkaManager\n"
            "async def main():\n"
            "    manager = KafkaManager(\n"
            "        asyncio.Event(), os.environ['SCRAPY_CFFI_KAFKA']\n"
            "    )\n"
            f"    await manager.produce('customRedisSpider_start', {start_url.encode()!r})\n"
            "    await manager.close()\n"
            "asyncio.run(main())\n"
        )
    with (log_dir / "enqueue.log").open("w", encoding="utf-8") as handle:
        subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(project),
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=True,
        )


def run_end_to_end_demo(
    name: str,
    project: Path,
    log_dir: Path,
    broker_environment: Optional[Dict[str, str]],
) -> None:
    http_port = available_port(18002)
    websocket_port = available_port(18765)
    configure_e2e_project(
        project,
        log_dir,
        broker_environment,
        http_port,
        websocket_port,
    )
    environment = project_environment(project, broker_environment)
    processes, handles = start_demo_servers(
        project,
        log_dir,
        http_port,
        websocket_port,
    )
    console_path = log_dir / "console.log"
    try:
        start_url = f"http://127.0.0.1:{http_port}"
        enqueue_start_request(name, project, environment, start_url, log_dir)
        with console_path.open("w", encoding="utf-8") as console:
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import asyncio\n"
                        "from runner import advance_main\n"
                        "async def verify():\n"
                        "    crawler, engine_task = await advance_main()\n"
                        "    try:\n"
                        "        await asyncio.sleep(6)\n"
                        "    finally:\n"
                        "        await crawler.shutdown()\n"
                        "    await asyncio.wait_for(engine_task, timeout=15)\n"
                        "asyncio.run(verify())\n"
                    ),
                ],
                cwd=str(project),
                env=environment,
                stdout=console,
                stderr=subprocess.STDOUT,
                timeout=30,
                check=True,
            )
    finally:
        for process in reversed(processes):
            stop_process(process)
        for handle in handles:
            handle.close()

    framework_log = log_dir / "demo.log"
    console_text = console_path.read_text(encoding="utf-8", errors="replace")
    websocket_text = (log_dir / "websocket_server.log").read_text(
        encoding="utf-8",
        errors="replace",
    )
    failures = []
    if not framework_log.is_file() or framework_log.stat().st_size == 0:
        failures.append("demo.log is missing or empty")
    if '"method":"GET"' not in console_text:
        failures.append("HTTP parse callback evidence is missing from console.log")
    if "received:" not in websocket_text:
        failures.append("WebSocket incremental request evidence is missing")
    if "Traceback (most recent call last)" in console_text:
        failures.append("crawler console contains a traceback")
    if "Traceback (most recent call last)" in websocket_text:
        failures.append("WebSocket server log contains a traceback")
    if failures:
        raise AssertionError(f"{name} end-to-end validation failed: {failures}")

    summary = (
        f"status=PASS\n"
        f"spider_mode={name}\n"
        f"http_url=http://127.0.0.1:{http_port}\n"
        f"websocket_url=ws://127.0.0.1:{websocket_port}\n"
        f"framework_log={framework_log.name}\n"
        f"console_log={console_path.name}\n"
        f"broker_log={'broker.log' if name != 'memory' else 'n/a'}\n"
        f"http_server_log=http_server.log\n"
        f"websocket_server_log=websocket_server.log\n"
    )
    (log_dir / "result.txt").write_text(summary, encoding="utf-8")


def compose(infra: Path, *args: str) -> None:
    run(
        [
            "docker",
            "compose",
            "--project-name",
            COMPOSE_PROJECT,
            "--env-file",
            str(infra / ".env"),
            "--file",
            str(infra / "docker-compose.yml"),
            *args,
        ]
    )


def available_port(preferred: int) -> int:
    # Avoid Windows' dynamic client-port range for Docker published ports.
    # Reusing a port from that range as both destination and ephemeral source
    # can make AMQP handshakes fail even though the container healthcheck passes.
    for port in range(preferred, preferred + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free local port found from {preferred}")


def prepare_infra(infra: Path) -> Dict[str, str]:
    redis_port = available_port(16379)
    rabbit_port = available_port(15682)
    rabbit_management_port = available_port(25682)
    kafka_port = available_port(19092)
    values = {
        "REDIS_PORT": str(redis_port),
        "RABBITMQ_PORT": str(rabbit_port),
        "RABBITMQ_MANAGEMENT_PORT": str(rabbit_management_port),
        "RABBITMQ_USER": "scrapy_cffi",
        "RABBITMQ_PASSWORD": "scrapy_cffi",
        "KAFKA_PORT": str(kafka_port),
        "KAFKA_ADVERTISED_HOST": "127.0.0.1",
    }
    source = (infra / ".env.example").read_text(encoding="utf-8")
    additions = "".join(f"\n{key}={value}" for key, value in values.items())
    (infra / ".env").write_text(source + additions + "\n", encoding="utf-8")

    environment = dict(os.environ)
    environment.update(
        SCRAPY_CFFI_REDIS_URL=f"redis://127.0.0.1:{redis_port}/0",
        SCRAPY_CFFI_AMQP_URL=(
            f"amqp://scrapy_cffi:scrapy_cffi@127.0.0.1:{rabbit_port}/"
        ),
        SCRAPY_CFFI_KAFKA=f"127.0.0.1:{kafka_port}",
    )
    return environment


def start_infra(infra: Path, services: List[str]) -> None:
    compose(infra, "up", "--detach", "--wait", *services)


def reset_infra(infra: Path) -> None:
    compose(infra, "down", "--volumes", "--remove-orphans")


def run_unit_check(target: str) -> None:
    module_name, function_name = target.rsplit(".", 1)
    print(f"\n>>> {target}", flush=True)
    module_path = ROOT / Path(*module_name.split(".")).with_suffix(".py")
    spec = importlib.util.spec_from_file_location(
        f"_scrapy_cffi_verify_{module_path.stem}",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load verification module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, function_name)
    if module_name.endswith("test_scheduler_smoke"):
        with tempfile.TemporaryDirectory(prefix="scrapy-cffi-unit-") as directory:
            function(Path(directory))
    else:
        function()


def verify_case(
    name: str,
    flag: str,
    unit_checks: List[str],
    broker_script: str,
    infra: Path,
    temp_root: Path,
    skip_infra: bool,
    broker_environment: Optional[Dict[str, str]],
    log_root: Path,
) -> None:
    print(f"\n{'=' * 16} {name} {'=' * 16}", flush=True)
    case_log_dir = log_root / name
    case_log_dir.mkdir(parents=True, exist_ok=True)
    project = generate_demo(temp_root / name, flag)
    verify_generated_project(project)

    services = {
        "redis": ["redis"],
        "rabbitmq": ["redis", "rabbitmq"],
        "kafka": ["redis", "kafka"],
    }.get(name, [])
    try:
        if services and not skip_infra:
            start_infra(infra, services)
        for target in unit_checks:
            run_unit_check(target)
        if broker_script and not skip_infra:
            run(
                [sys.executable, str(ROOT / broker_script), "single"],
                env=broker_environment,
                output_path=case_log_dir / "broker.log",
            )
        if not skip_infra:
            run_end_to_end_demo(
                name,
                project,
                case_log_dir,
                broker_environment,
            )
    except BaseException as exc:
        result_path = case_log_dir / "result.txt"
        if not result_path.exists():
            result_path.write_text(
                f"status=FAIL\nspider_mode={name}\nerror={exc!r}\n",
                encoding="utf-8",
            )
        raise
    finally:
        if services and not skip_infra:
            reset_infra(infra)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serially verify memory, Redis, RabbitMQ and Kafka demos."
    )
    parser.add_argument(
        "--skip-infra",
        action="store_true",
        help="Run generated-project/unit checks only; skip real local brokers.",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep the generated temporary demos for inspection.",
    )
    parser.add_argument(
        "--log-dir",
        help=(
            "Persistent verification log directory. Defaults to "
            "artifacts/demo-verification/<timestamp>."
        ),
    )
    args = parser.parse_args()

    if not args.skip_infra and shutil.which("docker") is None:
        raise RuntimeError("Docker CLI is required; use --skip-infra for unit-only checks")

    from scrapy_cffi.commands import geninfra

    managed = tempfile.mkdtemp(prefix="scrapy-cffi-demo-")
    temp_root = Path(managed)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_root = (
        Path(args.log_dir).resolve()
        if args.log_dir
        else ROOT / "artifacts" / "demo-verification" / timestamp
    )
    log_root.mkdir(parents=True, exist_ok=True)
    infra = temp_root / "infra"
    broker_environment = None
    active_mode = "initialization"
    try:
        if not args.skip_infra:
            geninfra.run(output_dir=str(infra))
            broker_environment = prepare_infra(infra)
        cases = [
            (
                "memory",
                "",
                ["tests.test_scheduler_smoke.test_memory_scheduler_init"],
                "",
            ),
            (
                "redis",
                "-r",
                [
                    "tests.test_scheduler_smoke.test_redis_scheduler_init",
                    "tests.test_kafka_scheduler.test_redis_scheduler_requeues_unfinished_request_for_ctrl_c",
                ],
                "tests/test_broker/test_redis_broker.py",
            ),
            (
                "rabbitmq",
                "-m",
                [
                    "tests.test_scheduler_smoke.test_rabbitmq_scheduler_init",
                    "tests.test_kafka_scheduler.test_rabbit_scheduler_requeues_work_and_start_requests_for_ctrl_c",
                ],
                "tests/test_broker/test_rabbitmq_broker.py",
            ),
            (
                "kafka",
                "-k",
                [
                    "tests.test_scheduler_smoke.test_kafka_scheduler_init",
                    "tests.test_kafka_scheduler.test_kafka_work_and_start_topics_are_separate_and_manually_acked",
                ],
                "tests/test_broker/test_kafka_broker.py",
            ),
        ]
        for name, flag, targets, broker in cases:
            active_mode = name
            verify_case(
                name,
                flag,
                targets,
                broker,
                infra,
                temp_root,
                args.skip_infra,
                broker_environment,
                log_root,
            )
    except BaseException as exc:
        (log_root / "result.txt").write_text(
            (
                "status=FAIL\n"
                f"failed_mode={active_mode}\n"
                f"error={exc!r}\n"
                f"log_root={log_root}\n"
            ),
            encoding="utf-8",
        )
        raise
    finally:
        if not args.skip_infra and infra.exists():
            try:
                reset_infra(infra)
            except subprocess.CalledProcessError:
                pass
        if args.keep_workdir:
            print(f"\nGenerated demos kept at: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)

    overall = (
        "status=PASS\n"
        "modes=memory,redis,rabbitmq,kafka\n"
        f"log_root={log_root}\n"
        f"infra={'skipped' if args.skip_infra else 'verified-and-removed'}\n"
    )
    (log_root / "result.txt").write_text(overall, encoding="utf-8")
    print(
        "\nAll demo transports passed; disposable infra state was removed."
        f"\nVerification logs: {log_root}"
    )


if __name__ == "__main__":
    main()
