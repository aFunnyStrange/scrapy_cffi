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

REPO_ROOT = Path(__file__).resolve().parents[2]
ALL_MODES = ("memory", "redis", "rabbitmq", "kafka")
TOPOLOGIES = ("single", "sentinel", "cluster")
MODE_FLAGS = {
    "memory": (),
    "redis": ("-r",),
    "rabbitmq": ("-m",),
    "kafka": ("-k",),
    "tls": ("-tls",),
}


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    """Temporarily enter one generated project directory."""
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
    """Run one subprocess and persist its combined output and duration."""
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


def _cli_environment(*paths: Path) -> Dict[str, str]:
    """Build an environment that executes the checked-out framework code."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT), *(str(path) for path in paths), environment.get("PYTHONPATH", "")]
    )
    return environment


def _run_cli(
    arguments: Sequence[str],
    cwd: Path,
    log_path: Path,
) -> Tuple[bool, float]:
    """Exercise the same argparse composition root as the console script."""
    return _run_logged(
        [
            sys.executable,
            "-c",
            "from scrapy_cffi.commands.main import main; main()",
            *arguments,
        ],
        cwd,
        log_path,
        env=_cli_environment(cwd),
    )


def _generate_demo(
    work_root: Path,
    mode: str,
    log_path: Path,
) -> Tuple[Path, bool, float]:
    """Generate a Demo through the public CLI route."""
    case_root = work_root / mode
    case_root.mkdir(parents=True, exist_ok=True)
    passed, seconds = _run_cli(
        ["demo", *MODE_FLAGS[mode]],
        case_root,
        log_path,
    )
    return case_root / "demo", passed, seconds


def _verify_generated_project(
    project: Path,
    log_path: Path,
    require_default_spider: bool = True,
) -> Tuple[bool, float]:
    """Compile and import one generated user project."""
    environment = _cli_environment(project)
    default_assertion = (
        "assert runner.DEFAULT_SPIDER is not None; "
        if require_default_spider
        else "assert runner.DEFAULT_SPIDER is None; "
    )
    code = (
        "import compileall, runner, settings; "
        "assert compileall.compile_dir('.', quiet=1); "
        + default_assertion
        +
        "settings.create_settings(runner.DEFAULT_SPIDER)"
    )
    return _run_logged(
        [sys.executable, "-c", code],
        project,
        log_path,
        env=environment,
    )


def _cleanup_demo(project: Path, cleanup_log: Path) -> None:
    """Stop all generated Demo topologies after a verification phase."""
    cleanup_log.parent.mkdir(parents=True, exist_ok=True)
    with cleanup_log.open("a", encoding="utf-8") as output:
        for topology in TOPOLOGIES:
            subprocess.run(
                [sys.executable, "scripts/demo_docker.py", "down", topology],
                cwd=str(project),
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
            )


def _copy_demo_evidence(project: Path, destination: Path) -> None:
    """Copy generated runtime evidence into the release log directory."""
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
    """Write machine-readable and human-readable verification summaries."""
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
    """Execute the selected source, generator, and runtime verification matrix."""
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
            "scrapy-cffi test must run from a framework source checkout "
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

    startproject_root = work_root / "startproject"
    startproject_root.mkdir(parents=True, exist_ok=True)
    startproject_ok, startproject_seconds = _run_cli(
        ["startproject", "generated_project"],
        startproject_root,
        log_root / "startproject" / "cli-generate.log",
    )
    generated_project = startproject_root / "generated_project"
    if startproject_ok:
        import_ok, import_seconds = _verify_generated_project(
            generated_project,
            log_root / "startproject" / "generated-project.log",
            require_default_spider=False,
        )
    else:
        import_ok, import_seconds = False, 0.0
    results.extend(
        [
            {
                "scope": "startproject",
                "phase": "cli-generate",
                "passed": startproject_ok,
                "seconds": startproject_seconds,
                "log": "startproject/cli-generate.log",
            },
            {
                "scope": "startproject",
                "phase": "generate/import",
                "passed": import_ok,
                "seconds": import_seconds,
                "log": "startproject/generated-project.log",
            },
        ]
    )

    tls_project, tls_cli_ok, tls_cli_seconds = _generate_demo(
        work_root,
        "tls",
        log_root / "tls" / "cli-generate.log",
    )
    if tls_cli_ok:
        tls_import_ok, tls_import_seconds = _verify_generated_project(
            tls_project,
            log_root / "tls" / "generated-project.log",
        )
    else:
        tls_import_ok, tls_import_seconds = False, 0.0
    results.extend(
        [
            {
                "scope": "tls",
                "phase": "cli-generate",
                "passed": tls_cli_ok,
                "seconds": tls_cli_seconds,
                "log": "tls/cli-generate.log",
            },
            {
                "scope": "tls",
                "phase": "generate/import",
                "passed": tls_import_ok,
                "seconds": tls_import_seconds,
                "log": "tls/generated-project.log",
            },
        ]
    )

    for mode in selected_modes:
        project: Optional[Path] = None
        try:
            project, cli_ok, cli_seconds = _generate_demo(
                work_root,
                mode,
                log_root / mode / "cli-generate.log",
            )
            results.append(
                {
                    "scope": mode,
                    "phase": "cli-generate",
                    "passed": cli_ok,
                    "seconds": cli_seconds,
                    "log": "%s/cli-generate.log" % mode,
                }
            )
            if not cli_ok:
                continue
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
                if not no_interrupt and mode != "memory":
                    phase_commands.append(
                        (
                            "interrupt-%s" % topology,
                            ["verify-interrupt", topology],
                        )
                    )

            for phase, arguments in phase_commands:
                passed, seconds = _run_logged(
                    [sys.executable, "scripts/demo_docker.py"] + arguments,
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
