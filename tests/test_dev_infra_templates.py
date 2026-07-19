from pathlib import Path

from scrapy_cffi.commands import geninfra


SERVICE_NAMES = ("redis", "mysql", "postgres", "mongodb", "rabbitmq", "kafka")


def test_project_compose_contains_only_the_crawler_app():
    compose_path = (
        Path(__file__).parents[1]
        / "scrapy_cffi"
        / "templates"
        / "config"
        / "docker-compose.yml"
    )
    compose = compose_path.read_text(encoding="utf-8")

    assert "  app:\n" in compose
    assert "depends_on:" not in compose
    for service in SERVICE_NAMES:
        assert f"  {service}:\n" not in compose


def test_geninfra_generates_independent_dev_stack_and_reset_scripts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    geninfra.run()

    target = tmp_path / "infra"
    compose = (target / "docker-compose.yml").read_text(encoding="utf-8")
    for service in SERVICE_NAMES:
        assert f"  {service}:\n" in compose

    assert "apache/kafka:4.3.1" in compose
    assert "bitnami/kafka" not in compose
    assert not (target / "Dockerfile").exists()
    assert (target / ".env.example").is_file()
    assert (target / "production-endpoints.example.toml").is_file()
    assert (target / "init.ps1").is_file()
    assert (target / "reset.ps1").is_file()
    assert (target / "destroy.ps1").is_file()
    assert (target / "init.sh").is_file()
    assert (target / "reset.sh").is_file()
    assert (target / "destroy.sh").is_file()
    assert "workspace_slug" in (target / "reset.sh").read_text(encoding="utf-8")
    assert "down --volumes --remove-orphans" in (target / "reset.sh").read_text(
        encoding="utf-8"
    )


def test_geninfra_clean_preserves_developer_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    geninfra.run()
    env_path = tmp_path / "infra" / ".env"
    env_path.write_text("REDIS_PORT=6380\n", encoding="utf-8")

    geninfra.run(clean=True)

    assert env_path.read_text(encoding="utf-8") == "REDIS_PORT=6380\n"
    assert not (tmp_path / "infra" / "docker-compose.yml").exists()


def test_geninfra_all_generates_every_disposable_local_topology(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    geninfra.run(generate_all=True)

    target = tmp_path / "infra"
    for topology in (
        "redis-sentinel",
        "redis-cluster",
        "rabbitmq-cluster",
        "kafka-cluster",
    ):
        assert (target / topology / "docker-compose.yml").is_file()

    init_script = (target / "init.ps1").read_text(encoding="utf-8")
    assert "[ValidateSet(" in init_script
    assert '"redis-sentinel"' in init_script
    assert "workspaceSlug" in init_script
