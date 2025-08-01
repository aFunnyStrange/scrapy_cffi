import toml
from ..utils import load_settings_from_py
from pathlib import Path
from jinja2 import Template

def check_use_redis(project_path: Path, use_redis: bool=False, use_task: bool=False):
    config_path = project_path / "scrapy_cffi.toml"

    config_data = toml.load(config_path)
    if config_data.get("default"):
        if not use_task:
            use_task = config_data["default"].get("use_task", False)
        if use_redis and (not config_data["default"].get("use_redis", False)):
            config_data["default"]["use_redis"] = True
            with config_path.open("w", encoding="utf-8") as f:
                toml.dump(config_data, f)

            # Scheduler -> RedisScheduler
            settings_file = project_path / "spiders" / "settings.py" if use_task else project_path / "settings.py"
            settings_data = settings_file.read_text(encoding='utf-8')
            if 'def create_settings(spider_path, user_redis=False, *args, **kwargs):' in settings_data:
                settings_data = settings_data.replace('def create_settings(spider_path, user_redis=False, *args, **kwargs):', 'def create_settings(spider_path, user_redis=True, *args, **kwargs):')
                settings_file.write_text(settings_data, encoding="utf-8")
            # update config.py
            if use_task:
                task_config_path = project_path / "config.py"
                if task_config_path.exists():
                    task_config = load_settings_from_py(task_config_path, auto_upper=False)
                    if not task_config.get("redis_url"):
                        with task_config_path.open("a", encoding="utf-8") as f:
                            f.write('\nredis_url = "redis://127.0.0.1:6379"\n')
    return use_task

def run(spider_name: str, allow_domain: str, use_redis: bool, is_demo=False):
    from .base import find_project_root
    project_path = find_project_root()
    use_task = check_use_redis(project_path, use_redis)

    class_name = snake_to_camel(spider_name)
    base_class = "RedisSpider" if use_redis else "Spider"
    base_import = "scrapy_cffi.spiders"
    start_urls = f'redis_key = ""' if use_redis else f'start_urls = ["https://{allow_domain}"]'

    base = Path(__file__).parent.parent # scrapy_cffi
    template_dir = base / "templates"
    with open(template_dir / "spider.py.j2", "r", encoding="utf-8") as f:
        template: Template = Template(f.read())
    
    code = template.render(
        class_name=class_name,
        spider_name=spider_name,
        domain=allow_domain,
        base_class=base_class,
        base_import=base_import,
        start_urls=start_urls
    )
    target_file = project_path / "spiders" / "spiders" / f"{spider_name}.py" if use_task else project_path / "spiders" / f"{spider_name}.py" # use abspath
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(code, encoding="utf-8")

    # To avoid overwriting user-defined content, only spider templates should be regenerated; other files should be appended or updated dynamically.
    update_spiders_init(project_path, class_name, spider_name, use_task)
    if not is_demo:
        print(f"Spider created: {target_file}")

# Use this to automatically convert snake_case to camelCase.
def snake_to_camel(name: str) -> str:
    return ''.join(word.capitalize() for word in name.split('_')) + "Spider"

# auto import
def update_spiders_init(project_path: Path, class_name: str, spider_name: str, use_task: bool):
    init_path =project_path / "spiders" / "spiders" / "__init__.py" if use_task else project_path / "spiders" / "__init__.py"
    import_line = f"from .{spider_name} import {class_name}\n"

    if not init_path.exists():
        init_path.write_text(import_line, encoding="utf-8")
        return

    init_data = init_path.read_text(encoding='utf-8')
    if import_line in init_data:
        return
    with open(init_path, "a", encoding="utf-8") as f:
        f.write(import_line)