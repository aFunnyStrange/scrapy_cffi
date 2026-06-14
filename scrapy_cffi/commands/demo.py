from pathlib import Path
from typing import List
from ._template_build import copytree_merge_text_safe, read_text_template, write_utf8_file


def copytree_merge(src: Path, dst: Path) -> None:
    copytree_merge_text_safe(src, dst)


def run(use_redis: bool, use_rabbitmq: bool, use_kafka: bool):
    base = Path(__file__).parent.parent
    template_dir = base / "templates"
    target: Path = Path.cwd() / "demo"

    from .base import find_project_root
    from .genspider import check_config

    project_path = find_project_root(is_demo=True)
    check_config(project_path, use_redis=use_redis, use_rabbitmq=use_rabbitmq, use_kafka=use_kafka)

    settings_path = target / "settings.py"
    settings_code = read_text_template(settings_path)
    settings_code = settings_code.replace("# settings.EXTENSIONS_PATH", "settings.EXTENSIONS_PATH")
    settings_code = settings_code.replace("# settings.ITEM_PIPELINES_PATH", "settings.ITEM_PIPELINES_PATH")
    settings_code = settings_code.replace(
        '# "interceptors.CustomDownloadInterceptor1"',
        '"interceptors.CustomDownloadInterceptor1"',
    )
    settings_code = settings_code.replace(
        '# "interceptors.CustomDownloadInterceptor2"',
        '"interceptors.CustomDownloadInterceptor2"',
    )
    write_utf8_file(settings_path, settings_code)

    spider_dir = target / "spiders"
    demo_spiders_dir = template_dir / "demo_spider"

    copytree_merge(template_dir / "server", target)
    if use_rabbitmq:
        push_demo = template_dir / "spiders" / "push_rabbitmq_demo.py"
        if push_demo.is_file():
            write_utf8_file(target / "push_rabbitmq_demo.py", read_text_template(push_demo))
    else:
        maybe_push_demo = target / "push_rabbitmq_demo.py"
        if maybe_push_demo.exists():
            maybe_push_demo.unlink()

    legacy_readme = target / "readme.txt"
    if legacy_readme.exists():
        legacy_readme.unlink()

    if use_rabbitmq or use_redis:
        demo_spider_files = ["customRedisSpider", "studentSpider"]
        for demo_spider in demo_spider_files:
            demo_spider_path = demo_spiders_dir / f"{demo_spider}.py"
            target_spider_path = spider_dir / f"{demo_spider}.py"
            demo_spider_code = read_text_template(demo_spider_path)
            target_spider_path.parent.mkdir(parents=True, exist_ok=True)
            if use_rabbitmq:
                demo_spider_code = demo_spider_code.replace(
                    "from scrapy_cffi.spiders.redis import RedisSpider",
                    "from scrapy_cffi.spiders.rabbitmq import RabbitmqSpider",
                )
                demo_spider_code = demo_spider_code.replace("(RedisSpider)", "(RabbitmqSpider)")
                demo_spider_code = demo_spider_code.replace(
                    'redis_key = "customRedisSpider_test"',
                    'rabbitmq_queue = "scrapy_cffi"',
                )
            write_utf8_file(target_spider_path, demo_spider_code)

        update_spiders_path(
            project_path=target,
            demo_spiders_dir=demo_spiders_dir,
            demo_spider_files=demo_spider_files,
            spider_dir=spider_dir,
            use_redis=use_redis,
            use_rabbitmq=use_rabbitmq,
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

        update_spiders_path(
            project_path=target,
            demo_spiders_dir=demo_spiders_dir,
            demo_spider_files=demo_spider_files,
            spider_dir=spider_dir,
            use_redis=use_redis,
            use_rabbitmq=use_rabbitmq,
        )

    print("Project 'demo' created.")
    demo_readme = template_dir / "demo_README.md"
    if demo_readme.exists():
        write_utf8_file(target / "README.md", read_text_template(demo_readme))
        print("  See README.md in demo/ for single-machine steps.")


def update_spiders_path(
    project_path: Path,
    demo_spiders_dir: Path,
    demo_spider_files: List,
    spider_dir: Path,
    use_redis: bool,
    use_rabbitmq: bool,
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
