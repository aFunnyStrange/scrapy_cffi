import json


def test_quick_verifier_collects_all_results_and_writes_summary(
    tmp_path,
    monkeypatch,
):
    from scrapy_cffi.commands import verification

    (tmp_path / "tests").mkdir()
    monkeypatch.setattr(verification, "REPO_ROOT", tmp_path)

    def fake_run(command, cwd, log_path, env=None):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ok\n", encoding="utf-8")
        return True, 0.01

    def fake_generate(work_root, mode):
        project = work_root / mode / "demo"
        project.mkdir(parents=True)
        return project

    monkeypatch.setattr(verification, "_run_logged", fake_run)
    monkeypatch.setattr(verification, "_generate_demo", fake_generate)

    log_dir = tmp_path / "logs"
    result = verification.run(
        quick=True,
        modes=("memory", "redis"),
        topologies=("single", "sentinel", "cluster"),
        log_dir=str(log_dir),
    )

    assert result == 0
    summary = json.loads((log_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    assert [(item["scope"], item["phase"]) for item in summary["results"]] == [
        ("framework", "pytest"),
        ("memory", "generate/import"),
        ("memory", "plan-single"),
        ("redis", "generate/import"),
        ("redis", "plan-single"),
        ("redis", "plan-sentinel"),
        ("redis", "plan-cluster"),
    ]
    assert (log_dir / "summary.md").is_file()


def test_memory_is_not_run_for_distributed_only_topology(tmp_path, monkeypatch):
    from scrapy_cffi.commands import verification

    (tmp_path / "tests").mkdir()
    monkeypatch.setattr(verification, "REPO_ROOT", tmp_path)

    def fake_run(command, cwd, log_path, env=None):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ok\n", encoding="utf-8")
        return True, 0.01

    def fake_generate(work_root, mode):
        project = work_root / mode / "demo"
        project.mkdir(parents=True)
        return project

    monkeypatch.setattr(verification, "_run_logged", fake_run)
    monkeypatch.setattr(verification, "_generate_demo", fake_generate)

    log_dir = tmp_path / "cluster-logs"
    assert (
        verification.run(
            quick=True,
            modes=("memory", "redis"),
            topologies=("cluster",),
            log_dir=str(log_dir),
        )
        == 0
    )
    summary = json.loads((log_dir / "summary.json").read_text(encoding="utf-8"))
    phases = [
        (item["scope"], item["phase"])
        for item in summary["results"]
    ]
    assert not any(scope == "memory" for scope, _ in phases)
    assert ("memory", "plan-cluster") not in phases
    assert ("redis", "plan-cluster") in phases
