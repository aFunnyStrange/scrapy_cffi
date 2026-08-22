from pathlib import Path
from typing import List
from ._template_build import copytree_merge_text_safe, read_text_template, write_utf8_file
from .genspider import update_runner_default_spider
from . import _infra_templates


def copytree_merge(src: Path, dst: Path) -> None:
    copytree_merge_text_safe(src, dst)


def run(
    use_redis: bool,
    use_rabbitmq: bool,
    use_kafka: bool,
    use_tls: bool = False,
) -> None:
    """Generate one queue-backed, memory, or standalone TLS demo."""
    if use_tls and (use_redis or use_rabbitmq or use_kafka):
        raise ValueError("TLS demo cannot be combined with queue demo modes")
    base = Path(__file__).parent.parent
    template_dir = base / "templates"
    target: Path = Path.cwd() / "demo"

    from .base import find_project_root
    from .genspider import check_config

    project_path = find_project_root(is_demo=True)
    check_config(project_path, use_redis=use_redis, use_rabbitmq=use_rabbitmq, use_kafka=use_kafka)
    demo_mode = (
        "kafka"
        if use_kafka
        else "rabbitmq"
        if use_rabbitmq
        else "redis"
        if use_redis
        else "memory"
    )
    requirement = (
        "scrapy_cffi[kafka]"
        if use_kafka
        else "scrapy_cffi[rabbitmq]"
        if use_rabbitmq
        else "scrapy_cffi"
    )
    write_utf8_file(
        target / "requirements.txt",
        requirement
        + "\nfastapi>=0.115\n"
        + "uvicorn>=0.30\n"
        + "websockets>=15.0,<16\n"
        + "aioquic>=1.0,<1.3; python_version < '3.10'\n"
        + "aioquic>=1.3,<2; python_version >= '3.10'\n",
    )

    if use_tls:
        spider_dir = target / "spiders"
        tls_spider = template_dir / "demo_spider" / "tlsSpider.py"
        write_utf8_file(
            spider_dir / "tlsSpider.py",
            read_text_template(tls_spider),
        )
        update_spiders_package(
            demo_spider_files=["tlsSpider"],
            spider_dir=spider_dir,
        )
        update_runner_default_spider(target, "TlsSpider", "tlsSpider")
        tls_guide = template_dir / "tls_demo_GUIDE.md"
        write_utf8_file(target / "README.md", read_text_template(tls_guide))
        print("Project 'demo' created with the TLS inspection spider.")
        return

    _infra_templates.run(output_dir=str(target / "infra"), generate_all=True)
    management_dir = template_dir / "demo_management"
    copytree_merge(management_dir, target)
    demo_config = target / "demo_support" / "config.py"
    demo_config_code = read_text_template(demo_config).replace(
        "__SCRAPY_CFFI_DEMO_MODE__",
        demo_mode,
    )
    write_utf8_file(demo_config, demo_config_code)
    shell_manager = target / "scripts" / "docker-demo.sh"
    if shell_manager.exists():
        shell_manager.chmod(0o755)

    spider_dir = target / "spiders"
    demo_spiders_dir = template_dir / "demo_spider"

    copytree_merge(
        template_dir / "server" / "demo_server",
        target / "demo_support" / "server",
    )
    if use_rabbitmq:
        push_demo = template_dir / "spiders" / "push_rabbitmq_demo.py"
        if push_demo.is_file():
            write_utf8_file(
                target / "scripts" / "push_rabbitmq_demo.py",
                read_text_template(push_demo),
            )
    else:
        maybe_push_demo = target / "scripts" / "push_rabbitmq_demo.py"
        if maybe_push_demo.exists():
            maybe_push_demo.unlink()

    if use_kafka:
        push_demo = template_dir / "spiders" / "push_kafka_demo.py"
        if push_demo.is_file():
            write_utf8_file(
                target / "scripts" / "push_kafka_demo.py",
                read_text_template(push_demo),
            )
    else:
        maybe_push_demo = target / "scripts" / "push_kafka_demo.py"
        if maybe_push_demo.exists():
            maybe_push_demo.unlink()

    if use_rabbitmq or use_redis or use_kafka:
        demo_spider_files = ["customRedisSpider", "studentSpider"]
        for demo_spider in demo_spider_files:
            demo_spider_path = demo_spiders_dir / f"{demo_spider}.py"
            target_spider_path = spider_dir / f"{demo_spider}.py"
            demo_spider_code = read_text_template(demo_spider_path)
            target_spider_path.parent.mkdir(parents=True, exist_ok=True)
            if use_kafka:
                demo_spider_code = demo_spider_code.replace(
                    "from scrapy_cffi.spiders import RedisSpider",
                    "from scrapy_cffi.spiders import KafkaSpider",
                )
                demo_spider_code = demo_spider_code.replace("(RedisSpider)", "(KafkaSpider)")
                demo_spider_code = demo_spider_code.replace(
                    'redis_key = "customRedisSpider_test"',
                    'kafka_start_topic = "customRedisSpider_start"\n    kafka_topic = "customRedisSpider_requests"',
                )
            elif use_rabbitmq:
                demo_spider_code = demo_spider_code.replace(
                    "from scrapy_cffi.spiders import RedisSpider",
                    "from scrapy_cffi.spiders import RabbitmqSpider",
                )
                demo_spider_code = demo_spider_code.replace("(RedisSpider)", "(RabbitmqSpider)")
                demo_spider_code = demo_spider_code.replace(
                    'redis_key = "customRedisSpider_test"',
                    'rabbitmq_queue = "scrapy_cffi"',
                )
            write_utf8_file(target_spider_path, demo_spider_code)

        update_spiders_package(
            demo_spider_files=demo_spider_files,
            spider_dir=spider_dir,
        )
        update_runner_default_spider(
            target,
            "CustomRedisSpider",
            "customRedisSpider",
        )
    else:
        spider_dir.mkdir(parents=True, exist_ok=True)
        demo_spider_files = ["customSpider", "studentSpider"]
        for demo_spider in demo_spider_files:
            demo_spider_path = demo_spiders_dir / f"{demo_spider}.py"
            target_spider_path = spider_dir / f"{demo_spider}.py"
            demo_spider_code = read_text_template(demo_spider_path)
            target_spider_path.parent.mkdir(parents=True, exist_ok=True)
            write_utf8_file(target_spider_path, demo_spider_code)

        update_spiders_package(
            demo_spider_files=demo_spider_files,
            spider_dir=spider_dir,
        )
        update_runner_default_spider(target, "CustomSpider", "customSpider")

    print("Project 'demo' created.")
    demo_readme = template_dir / "demo_GUIDE.md"
    if demo_readme.exists():
        write_utf8_file(target / "README.md", read_text_template(demo_readme))
        print("  See README.md in demo/ for single-machine steps.")


def update_spiders_package(
    demo_spider_files: List,
    spider_dir: Path,
):
    spider_dir.mkdir(parents=True, exist_ok=True)
    keep = set(demo_spider_files)
    for py_file in spider_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        if py_file.stem not in keep:
            py_file.unlink()

    init_lines = []
    for spider_name in demo_spider_files:
        cls_name = spider_name[0].upper() + spider_name[1:] if spider_name else spider_name
        init_lines.append(f"from .{spider_name} import {cls_name}\n")
    write_utf8_file(spider_dir / "__init__.py", "".join(init_lines))
