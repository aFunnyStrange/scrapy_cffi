import shutil, toml
from pathlib import Path

def run(project_name, use_task: bool, is_demo=False):
    base = Path(__file__).parent.parent # scrapy_cffi
    template_dir = base / "templates"
    target: Path = Path.cwd() / project_name

    if target.exists():
        print(f"Error: Project '{project_name}' already exists.")
        return False
    
    if use_task:
        shutil.copytree(template_dir / "task", target)
    spiders_dir = target / "spiders" if use_task else target
    shutil.copytree(template_dir / "spiders", spiders_dir)
    shutil.copytree(template_dir / "js_path", target / "js_path")
    
    if use_task:
        # module path with `spiders`
        runner_path = spiders_dir / "runner.py"
        runner_code = runner_path.read_text(encoding='utf-8')
        runner_code = runner_code.replace('from settings import create_settings', 'from spiders.settings import create_settings')
        runner_path.write_text(runner_code, encoding='utf-8')

        settings_path = spiders_dir / "settings.py"
        settings_code = settings_path.read_text(encoding='utf-8')
        settings_code = settings_code.replace('"extensions.CustomExtension"', '"spiders.extensions.CustomExtension"')
        settings_code = settings_code.replace('"pipelines.CustomPipeline2"', '"spiders.pipelines.CustomPipeline2"')
        settings_code = settings_code.replace('"pipelines.CustomPipeline1"', '"spiders.pipelines.CustomPipeline1"')
        settings_code = settings_code.replace('"interceptors.CustomDownloadInterceptor1"', '"spiders.interceptors.CustomDownloadInterceptor1"')
        settings_code = settings_code.replace('"interceptors.CustomDownloadInterceptor2"', '"spiders.interceptors.CustomDownloadInterceptor2"')
        settings_path.write_text(settings_code, encoding='utf-8')

    config_data = {
        "default": {
            "project_name": project_name,
            "use_task": use_task
        }
    }
    config_path = target / "scrapy_cffi.toml"
    with config_path.open("w", encoding="utf-8") as f:
        toml.dump(config_data, f)
    if not is_demo:
        print(f"Project '{project_name}' created.")
        print(f"\tcd {project_name}")
        print(f"\tscrapy_cffi genspider <spider_name> <domain>")