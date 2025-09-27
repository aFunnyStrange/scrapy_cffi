import toml
from pathlib import Path
from jinja2 import Template

def check_config(project_path: Path, use_redis: bool=False, use_rabbitmq: bool=False, use_kafka: bool=False):
    config_path = project_path / "scrapy_cffi.toml"

    config_data = toml.load(config_path)
    if config_data.get("default"):
        if use_rabbitmq and (not config_data["default"].get("use_rabbitmq", False)):
            config_data["default"]["use_rabbitmq"] = True
            with config_path.open("w", encoding="utf-8") as f:
                toml.dump(config_data, f)

            # Scheduler -> RabbitMqScheduler
            settings_file = project_path / "settings.py"
            settings_data = settings_file.read_text(encoding='utf-8')
            if 'used_rabbitmq=False,' in settings_data:
                settings_data = settings_data.replace('used_rabbitmq=False,', 'used_rabbitmq=True,')
                settings_file.write_text(settings_data, encoding="utf-8")
        elif use_redis and (not config_data["default"].get("use_redis", False)):
            config_data["default"]["use_redis"] = True
            with config_path.open("w", encoding="utf-8") as f:
                toml.dump(config_data, f)

            # Scheduler -> RedisScheduler
            settings_file = project_path / "settings.py"
            settings_data = settings_file.read_text(encoding='utf-8')
            if 'used_redis=False,' in settings_data:
                settings_data = settings_data.replace('used_redis=False,', 'used_redis=True,')
                settings_file.write_text(settings_data, encoding="utf-8")

        if use_kafka and (not config_data["default"].get("use_kafka", False)):
            config_data["default"]["use_kafka"] = True
            with config_path.open("w", encoding="utf-8") as f:
                toml.dump(config_data, f)

            settings_file = project_path / "settings.py"
            settings_data = settings_file.read_text(encoding='utf-8')
            if 'used_kafka=False,' in settings_data:
                settings_data = settings_data.replace('used_kafka=False,', 'used_kafka=True,')
                settings_file.write_text(settings_data, encoding="utf-8")

def run(spider_name: str, allow_domain: str, use_redis: bool, use_rabbitmq: bool, use_kafka: bool, is_demo=False):
    from .base import find_project_root
    project_path = find_project_root()
    check_config(project_path, use_redis, use_rabbitmq, use_kafka)

    class_name = snake_to_camel(spider_name)

    if use_rabbitmq:
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