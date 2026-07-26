"""Manage project-local, development-only Docker infrastructure."""

from pathlib import Path
import re
import shutil
import subprocess
from typing import List, NamedTuple, Optional, Sequence

import toml

from . import _infra_templates


ALL_SERVICES = (
    "redis",
    "mysql",
    "postgres",
    "mongodb",
    "rabbitmq",
    "kafka",
)
TOPOLOGIES = ("single", "sentinel", "cluster")


class Stack(NamedTuple):
    project_name: str
    compose_file: Path
    services: List[str]


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9_-]+", "_", value.lower()).strip("_")
    return result or "project"


def default_project_prefix() -> str:
    return "scrapy_cffi"


def _project_prefix(infra_dir: Path) -> str:
    project_dir = infra_dir.parent.resolve()
    config_path = project_dir / "scrapy_cffi.toml"
    if config_path.is_file():
        try:
            default = toml.load(config_path).get("default", {})
            configured = default.get("infra_project_name")
            if isinstance(configured, str) and configured.strip():
                return _slug(configured)
        except (OSError, TypeError, toml.TomlDecodeError):
            pass
    return default_project_prefix()


def build_stacks(
    infra_dir: Path,
    topology: str,
    services: Optional[Sequence[str]] = None,
    project_name: Optional[str] = None,
) -> List[Stack]:
    selected = list(dict.fromkeys(services or ALL_SERVICES))
    unknown = sorted(set(selected) - set(ALL_SERVICES))
    if unknown:
        raise ValueError("Unsupported services: %s" % ", ".join(unknown))
    prefix = _slug(project_name) if project_name else _project_prefix(infra_dir)

    if topology == "single":
        return [
            Stack(
                "%s_single" % prefix,
                infra_dir / "docker-compose.yml",
                selected if services is not None else [],
            )
        ]

    result = []
    base_services = [
        service
        for service in selected
        if service not in ("redis", "rabbitmq", "kafka")
    ]
    if topology == "sentinel":
        if "redis" in selected:
            result.append(
                Stack(
                    "%s_redis_sentinel" % prefix,
                    infra_dir / "redis-sentinel" / "docker-compose.yml",
                    [],
                )
            )
        base_services.extend(
            service
            for service in ("rabbitmq", "kafka")
            if service in selected
        )
    elif topology == "cluster":
        for service in ("redis", "rabbitmq", "kafka"):
            if service not in selected:
                continue
            template_name = "%s-cluster" % service
            result.append(
                Stack(
                    "%s_%s_cluster" % (prefix, service),
                    infra_dir / template_name / "docker-compose.yml",
                    [],
                )
            )
    else:
        raise ValueError("Unsupported topology: %s" % topology)

    if base_services:
        result.append(
            Stack(
                "%s_single_aux" % prefix,
                infra_dir / "docker-compose.yml",
                base_services,
            )
        )
    return result


def _ensure_templates(infra_dir: Path) -> None:
    required = (
        infra_dir / "docker-compose.yml",
        infra_dir / "redis-sentinel" / "docker-compose.yml",
        infra_dir / "redis-cluster" / "docker-compose.yml",
        infra_dir / "rabbitmq-cluster" / "docker-compose.yml",
        infra_dir / "kafka-cluster" / "docker-compose.yml",
    )
    if all(path.is_file() for path in required):
        return
    _infra_templates.run(
        output_dir=str(infra_dir),
        generate_all=True,
        overwrite=False,
    )


def _ensure_env(infra_dir: Path) -> None:
    target = infra_dir / ".env"
    source = infra_dir / ".env.example"
    if not target.exists():
        shutil.copyfile(source, target)
        print("Created %s from .env.example" % target)


def _compose_command(stack: Stack, infra_dir: Path, args: Sequence[str]) -> List[str]:
    command = [
        "docker",
        "compose",
        "--project-name",
        stack.project_name,
        "--file",
        str(stack.compose_file),
    ]
    env_file = infra_dir / ".env"
    if stack.compose_file.parent == infra_dir and env_file.exists():
        command.extend(["--env-file", str(env_file)])
    command.extend(args)
    return command


def _execute(
    command: Sequence[str],
    cwd: Path,
    check: bool = True,
) -> int:
    print("+ %s" % subprocess.list2cmdline(list(command)), flush=True)
    return subprocess.run(list(command), cwd=str(cwd), check=check).returncode


def run(
    action: str,
    output_dir: str = "infra",
    topology: str = "single",
    services: Optional[Sequence[str]] = None,
    project_name: Optional[str] = None,
) -> None:
    infra_dir = (Path.cwd() / output_dir).resolve()
    if action == "generate":
        _infra_templates.run(output_dir=str(infra_dir), generate_all=True)
        return
    if action == "clean":
        _infra_templates.run(output_dir=str(infra_dir), clean=True)
        return

    _ensure_templates(infra_dir)
    stacks = build_stacks(infra_dir, topology, services, project_name)

    if action == "plan":
        for stack in stacks:
            stack_services = ",".join(stack.services) if stack.services else "all"
            print(
                "%s | %s | %s"
                % (stack.project_name, stack.compose_file, stack_services)
            )
        return

    if shutil.which("docker") is None:
        raise RuntimeError("Docker CLI was not found")
    _ensure_env(infra_dir)

    if action in ("down", "destroy"):
        for stack in reversed(stacks):
            _execute(
                _compose_command(
                    stack,
                    infra_dir,
                    ["down", "--volumes", "--remove-orphans"],
                ),
                infra_dir,
                check=False,
            )
        return

    if action == "reset":
        for stack in reversed(stacks):
            _execute(
                _compose_command(
                    stack,
                    infra_dir,
                    ["down", "--volumes", "--remove-orphans"],
                ),
                infra_dir,
                check=False,
            )
        action = "up"

    if action in ("up", "init"):
        for stack in stacks:
            args = ["up", "--detach", "--wait"]
            args.extend(stack.services)
            _execute(_compose_command(stack, infra_dir, args), infra_dir)
        print("Development credentials: %s" % (infra_dir / "README.md"))
        return

    if action == "status":
        for stack in stacks:
            _execute(
                _compose_command(stack, infra_dir, ["ps"]),
                infra_dir,
                check=False,
            )
        return

    if action == "config":
        for stack in stacks:
            _execute(
                _compose_command(stack, infra_dir, ["config", "--quiet"]),
                infra_dir,
            )
        return

    raise ValueError("Unsupported infra action: %s" % action)
