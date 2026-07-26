"""One-command release verification for the framework source checkout."""

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from . import demo, startproject


REPO_ROOT = Path(__file__).resolve().parents[2]
ALL_MODES = ("memory", "redis", "rabbitmq", "kafka")
TOPOLOGIES = ("single", "sentinel", "cluster")
MODE_FLAGS = {
    "memory": (False, False, False),
    "redis": (True, False, False),
    "rabbitmq": (False, True, False),
    "kafka": (False, False, True),
}


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _run_logged(
    command: Sequence[str],
    cwd: Path,
    log_path: Path,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[bool, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as output:
        result = subprocess.run(
            list(command),
            cwd=str(cwd),
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return result.returncode == 0, time.monotonic() - started


def _generate_demo(work_root: Path, mode: str) -> Path:
    case_root = work_root / mode
    case_root.mkdir(parents=True, exist_ok=True)
    with _working_directory(case_root):
        if startproject.run("demo", is_demo=True) is not None:
            raise RuntimeError("Could not generate %s demo" % mode)
        demo.run(*MODE_FLAGS[mode])
    return case_root / "demo"


def _verify_generated_project(project: Path, log_path: Path) -> Tuple[bool, float]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT), str(project), environment.get("PYTHONPATH", "")]
    )
    code = (
        "import compileall, runner, settings; "
        "assert compileall.compile_dir('.', quiet=1); "
        "assert runner.DEFAULT_SPIDER is not None; "
        "settings.create_settings(runner.DEFAULT_SPIDER)"
    )
    return _run_logged(
        [sys.executable, "-c", code],
        project,
        log_path,
        env=environment,
    )


def _cleanup_demo(project: Path, cleanup_log: Path) -> None:
    cleanup_log.parent.mkdir(parents=True, exist_ok=True)
    with cleanup_log.open("a", encoding="utf-8") as output:
        for topology in TOPOLOGIES:
            subprocess.run(
                [sys.executable, "demo_docker.py", "down", topology],
                cwd=str(project),
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
            )


def _copy_demo_evidence(project: Path, destination: Path) -> None:
    source = project / "artifacts" / "demo-verification"
    if not source.exists():
        return
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _write_summary(
    log_root: Path,
    results: List[Dict[str, object]],
    work_root: Optional[Path],
) -> bool:
    passed = all(bool(item["passed"]) for item in results)
    payload = {
        "status": "PASS" if passed else "FAIL",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "work_root": str(work_root) if work_root else None,
        "results": results,
    }
    (log_root / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# scrapy-cffi verification",
        "",
        "Overall: **%s**" % payload["status"],
        "",
        "| Scope | Phase | Result | Seconds | Log |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for item in results:
        lines.append(
            "| {scope} | {phase} | {result} | {seconds:.2f} | {log} |".format(
                scope=item["scope"],
                phase=item["phase"],
                result="PASS" if item["passed"] else "FAIL",
                seconds=float(item["seconds"]),
                log=item["log"],
            )
        )
    (log_root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\nVerification summary")
    print("-" * 72)
    for item in results:
        print(
            "{:<10} {:<20} {:<4} {:>7.2f}s".format(
                item["scope"],
                item["phase"],
                "PASS" if item["passed"] else "FAIL",
                float(item["seconds"]),
            )
        )
    print("-" * 72)
    print("Overall: %s" % payload["status"])
    print("Logs: %s" % log_root)
    return passed


def run(
    quick: bool = False,
    no_interrupt: bool = False,
    modes: Optional[Sequence[str]] = None,
    topologies: Optional[Sequence[str]] = None,
    log_dir: Optional[str] = None,
    keep_workdir: bool = False,
) -> int:
    selected_modes = tuple(modes or ALL_MODES)
    selected_topologies = tuple(topologies or TOPOLOGIES)
    invalid = sorted(set(selected_modes).difference(ALL_MODES))
    if invalid:
        raise ValueError("Unknown verification modes: %s" % ", ".join(invalid))
    invalid_topologies = sorted(set(selected_topologies).difference(TOPOLOGIES))
    if invalid_topologies:
        raise ValueError(
            "Unknown verification topologies: %s"
            % ", ".join(invalid_topologies)
        )
    if "single" not in selected_topologies:
        selected_modes = tuple(
            mode for mode in selected_modes if mode != "memory"
        )
    if not (REPO_ROOT / "tests").is_dir():
        raise RuntimeError(
            "scrapy-cffi verify must run from a framework source checkout "
            "that contains tests/"
        )
    if not quick and shutil.which("docker") is None:
        raise RuntimeError("Docker CLI is required; use --quick without Docker")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_root = (
        Path(log_dir).resolve()
        if log_dir
        else REPO_ROOT / "artifacts" / "release-verification" / timestamp
    )
    log_root.mkdir(parents=True, exist_ok=True)
    managed = tempfile.mkdtemp(prefix="scrapy-cffi-verify-")
    work_root = Path(managed)
    results: List[Dict[str, object]] = []

    pytest_ok, pytest_seconds = _run_logged(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--basetemp=%s" % (work_root / "pytest"),
            "-p",
            "no:cacheprovider",
        ],
        REPO_ROOT,
        log_root / "pytest.log",
    )
    results.append(
        {
            "scope": "framework",
            "phase": "pytest",
            "passed": pytest_ok,
            "seconds": pytest_seconds,
            "log": "pytest.log",
        }
    )

    for mode in selected_modes:
        project: Optional[Path] = None
        try:
            project = _generate_demo(work_root, mode)
            generated_ok, generated_seconds = _verify_generated_project(
                project,
                log_root / mode / "generated-project.log",
            )
            results.append(
                {
                    "scope": mode,
                    "phase": "generate/import",
                    "passed": generated_ok,
                    "seconds": generated_seconds,
                    "log": "%s/generated-project.log" % mode,
                }
            )

            applicable_topologies = (
                ("single",) if mode == "memory" else selected_topologies
            )
            phase_commands = []
            for topology in applicable_topologies:
                if quick:
                    phase_commands.append(
                        (
                            "plan-%s" % topology,
                            ["plan", topology],
                        )
                    )
                    continue
                phase_commands.append(
                    (
                        "crawl-%s" % topology,
                        ["verify", topology],
                    )
                )
                if not no_interrupt:
                    phase_commands.append(
                        (
                            "interrupt-%s" % topology,
                            ["verify-interrupt", topology],
                        )
                    )

            for phase, arguments in phase_commands:
                passed, seconds = _run_logged(
                    [sys.executable, "demo_docker.py"] + arguments,
                    project,
                    log_root / mode / ("%s.log" % phase),
                )
                results.append(
                    {
                        "scope": mode,
                        "phase": phase,
                        "passed": passed,
                        "seconds": seconds,
                        "log": "%s/%s.log" % (mode, phase),
                    }
                )
                if not quick:
                    _copy_demo_evidence(
                        project,
                        log_root / mode / ("%s-evidence" % phase),
                    )
        except BaseException as exc:
            error_log = log_root / mode / "orchestrator-error.log"
            error_log.parent.mkdir(parents=True, exist_ok=True)
            error_log.write_text(repr(exc) + "\n", encoding="utf-8")
            results.append(
                {
                    "scope": mode,
                    "phase": "orchestrator",
                    "passed": False,
                    "seconds": 0.0,
                    "log": "%s/orchestrator-error.log" % mode,
                }
            )
        finally:
            if project is not None:
                if not quick:
                    _cleanup_demo(project, log_root / mode / "cleanup.log")
                if quick:
                    _copy_demo_evidence(project, log_root / mode / "evidence")

    retained_work_root = work_root if keep_workdir else None
    passed = _write_summary(log_root, results, retained_work_root)
    if keep_workdir:
        print("Generated projects: %s" % work_root)
    else:
        shutil.rmtree(work_root, ignore_errors=True)
    return 0 if passed else 1


__all__ = ["ALL_MODES", "TOPOLOGIES", "run"]
