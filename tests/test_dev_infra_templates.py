from pathlib import Path

from scrapy_cffi.commands import _infra_templates, infra


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


def test_infra_templates_generate_independent_dev_stack_and_reset_scripts(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    _infra_templates.run()

    target = tmp_path / "infra"
    compose = (target / "docker-compose.yml").read_text(encoding="utf-8")
    for service in SERVICE_NAMES:
        assert f"  {service}:\n" in compose

    assert "apache/kafka:4.3.1" in compose
    assert "bitnami/kafka" not in compose
    assert 'MYSQL_ROOT_HOST: "${MYSQL_ROOT_HOST:-%}"' in compose
    assert not (target / "Dockerfile").exists()
    assert (target / ".env.example").is_file()
    assert (target / "production-endpoints.example.toml").is_file()
    assert (target / "init.ps1").is_file()
    assert (target / "reset.ps1").is_file()
    assert (target / "destroy.ps1").is_file()
    assert (target / "init.sh").is_file()
    assert (target / "reset.sh").is_file()
    assert (target / "destroy.sh").is_file()
    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "| MySQL | `root` | `123456` |" in readme
    assert "| PostgreSQL | `postgres` | `123456` | `app_db` |" in readme
    assert "| MongoDB | - | - | Authentication disabled;" in readme
    assert "Database initialization variables only apply" in readme
    assert "infra_project_name" in (target / "reset.sh").read_text(encoding="utf-8")
    assert "down --volumes --remove-orphans" in (target / "reset.sh").read_text(
        encoding="utf-8"
    )


def test_infra_templates_clean_preserves_developer_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _infra_templates.run()
    env_path = tmp_path / "infra" / ".env"
    env_path.write_text("REDIS_PORT=6380\n", encoding="utf-8")

    _infra_templates.run(clean=True)

    assert env_path.read_text(encoding="utf-8") == "REDIS_PORT=6380\n"
    assert not (tmp_path / "infra" / "docker-compose.yml").exists()


def test_infra_templates_generate_every_disposable_local_topology(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    _infra_templates.run(generate_all=True)

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
    assert "infra_project_name" in init_script
    kafka_cluster = (
        target / "kafka-cluster" / "docker-compose.yml"
    ).read_text(encoding="utf-8")
    assert "kafka-consumer-groups.sh" in kafka_cluster


def test_infra_cli_builds_whole_single_sentinel_and_cluster_plans(tmp_path):
    infra_dir = tmp_path / "infra"

    single = infra.build_stacks(
        infra_dir,
        "single",
        ("redis", "rabbitmq", "kafka"),
        "case",
    )
    assert len(single) == 1
    assert single[0].services == ["redis", "rabbitmq", "kafka"]

    sentinel = infra.build_stacks(
        infra_dir,
        "sentinel",
        ("redis", "rabbitmq", "kafka"),
        "case",
    )
    assert [stack.compose_file.parent.name for stack in sentinel] == [
        "redis-sentinel",
        "infra",
    ]
    assert sentinel[-1].services == ["rabbitmq", "kafka"]

    cluster = infra.build_stacks(
        infra_dir,
        "cluster",
        ("redis", "rabbitmq", "kafka"),
        "case",
    )
    assert [stack.compose_file.parent.name for stack in cluster] == [
        "redis-cluster",
        "rabbitmq-cluster",
        "kafka-cluster",
    ]


def test_single_without_services_lets_compose_start_defined_services(tmp_path):
    stacks = infra.build_stacks(
        tmp_path / "infra",
        "single",
        project_name="case",
    )

    assert len(stacks) == 1
    assert stacks[0].services == []


def test_infra_project_prefix_comes_from_scrapy_cffi_toml(tmp_path):
    (tmp_path / "scrapy_cffi.toml").write_text(
        '[default]\ninfra_project_name = "my_unique_crawler_dev"\n',
        encoding="utf-8",
    )

    assert infra._project_prefix(tmp_path / "infra") == "my_unique_crawler_dev"


def test_automatic_template_completion_preserves_custom_images(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    _infra_templates.run()
    compose_path = tmp_path / "infra" / "docker-compose.yml"
    compose_path.write_text(
        compose_path.read_text(encoding="utf-8").replace(
            "redis:7-alpine",
            "example.local/redis:custom",
        ),
        encoding="utf-8",
    )

    infra.run(
        "plan",
        topology="cluster",
        services=("redis", "rabbitmq", "kafka"),
        project_name="case",
    )

    assert "example.local/redis:custom" in compose_path.read_text(encoding="utf-8")
    assert (tmp_path / "infra" / "kafka-cluster" / "docker-compose.yml").is_file()


def test_infra_cli_plan_auto_generates_templates(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    infra.run(
        "plan",
        topology="cluster",
        services=("redis", "rabbitmq", "kafka"),
        project_name="case",
    )

    output = capsys.readouterr().out
    assert "redis-cluster" in output
    assert "rabbitmq-cluster" in output
    assert "kafka-cluster" in output
