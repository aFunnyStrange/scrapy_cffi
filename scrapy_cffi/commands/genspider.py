import toml
from pathlib import Path
from jinja2 import Template

def check_config(project_path: Path, use_redis: bool=False, use_rabbitmq: bool=False, use_kafka: bool=False):
    config_path = project_path / "scrapy_cffi.toml"

    config_data = toml.load(config_path)
    defaults = config_data.setdefault("default", {})
    changed = False
    for key, enabled in (
        ("use_redis", use_redis),
        ("use_rabbitmq", use_rabbitmq),
        ("use_kafka", use_kafka),
    ):
        if enabled and not defaults.get(key, False):
            defaults[key] = True
            changed = True
    if changed:
        with config_path.open("w", encoding="utf-8") as f:
            toml.dump(config_data, f)

def run(spider_name: str, allow_domain: str, use_redis: bool, use_rabbitmq: bool, use_kafka: bool, is_demo=False):
    from .base import find_project_root
    project_path = find_project_root()
    check_config(project_path, use_redis, use_rabbitmq, use_kafka)

    class_name = snake_to_camel(spider_name)

    if use_kafka:
        import_path = "from scrapy_cffi.spiders.kafka import KafkaSpider"
        base_class = "KafkaSpider"
        start_urls = f'kafka_start_topic = "{spider_name}_start"\n    kafka_topic = "{spider_name}_requests"'
    elif use_rabbitmq:
        import_path = "from scrapy_cffi.spiders.rabbitmq import RabbitmqSpider"
        base_class = "RabbitmqSpider"
        start_urls = 'rabbitmq_queue = ""'
    elif use_redis:
        import_path = "from scrapy_cffi.spiders.redis import RedisSpider"
        base_class = "RedisSpider"
        start_urls = 'redis_key = ""'
    else:
        import_path = "from scrapy_cffi.spiders import Spider"
        base_class = "Spider"
        start_urls = f'start_urls = ["https://{allow_domain}"]'

    base = Path(__file__).parent.parent # scrapy_cffi
    template_dir = base / "templates"
    with open(template_dir / "spider.py.j2", "r", encoding="utf-8") as f:
        template: Template = Template(f.read())
    
    code = template.render(
        class_name=class_name,
        spider_name=spider_name,
        domain=allow_domain,
        import_path=import_path,
        base_class=base_class,
        start_urls=start_urls
    )
    target_file = project_path / "spiders" / f"{spider_name}.py" # use abspath
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(code, encoding="utf-8")

    # To avoid overwriting user-defined content, only spider templates should be regenerated; other files should be appended or updated dynamically.
    update_spiders_init(project_path, class_name, spider_name)
    update_runner_default_spider(project_path, class_name, spider_name)
    if not is_demo:
        print(f"Spider created: {target_file}")

# Use this to automatically convert snake_case to camelCase.
def snake_to_camel(name: str) -> str:
    return ''.join(word.capitalize() for word in name.split('_')) + "Spider"

# auto import
def update_spiders_init(project_path: Path, class_name: str, spider_name: str):
    init_path = project_path / "spiders" / "__init__.py"
    import_line = f"from .{spider_name} import {class_name}\n"

    if not init_path.exists():
        init_path.write_text(import_line, encoding="utf-8")
        return

    init_data = init_path.read_text(encoding='utf-8')
    if import_line in init_data:
        return
    with open(init_path, "a", encoding="utf-8") as f:
        f.write(import_line)


def update_runner_default_spider(
    project_path: Path,
    class_name: str,
    spider_module: str,
) -> None:
    """Bind generated runner helpers to a real class so IDEs can follow it."""
    runner_path = project_path / "runner.py"
    if not runner_path.is_file():
        return

    start_marker = "# <scrapy-cffi:default-spider>"
    end_marker = "# </scrapy-cffi:default-spider>"
    runner_data = runner_path.read_text(encoding="utf-8")
    start = runner_data.find(start_marker)
    end = runner_data.find(end_marker)
    if start < 0 or end < 0 or end < start:
        return
    end += len(end_marker)
    replacement = (
        f"{start_marker}\n"
        f"from spiders.{spider_module} import {class_name}\n"
        f"DEFAULT_SPIDER: Type[BaseSpider] = {class_name}\n"
        f"{end_marker}"
    )
    runner_path.write_text(
        runner_data[:start] + replacement + runner_data[end:],
        encoding="utf-8",
    )
