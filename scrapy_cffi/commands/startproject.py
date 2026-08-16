"""Generate an IDE-friendly scrapy_cffi project from bundled templates."""

from pathlib import Path

import toml

from ._template_build import copytree_merge_text_safe, read_text_template, write_utf8_file
from .infra import default_project_prefix


def run(project_name, is_demo=False):
    """Create a normal or Demo project and its optional profile reference."""
    base = Path(__file__).parent.parent
    template_dir = base / "templates"
    target: Path = Path.cwd() / project_name

    if target.exists():
        print(f"Error: Project '{project_name}' already exists.")
        return False

    copytree_merge_text_safe(
        template_dir / "spiders",
        target,
        skip_files={"push_kafka_demo.py", "push_rabbitmq_demo.py"},
    )
    copytree_merge_text_safe(template_dir / "js_path", target / "js_path")
    copytree_merge_text_safe(template_dir / "profiles", target / "profiles")
    for docker_file in [
        "Dockerfile",
        "Dockerfile.dockerignore",
        "docker-compose.yml",
    ]:
        docker_path = template_dir / "config" / docker_file
        target_path = target / "docker" / docker_file
        target_path.parent.mkdir(parents=True, exist_ok=True)
        write_utf8_file(target_path, read_text_template(docker_path))

    for project_file in [
        "requirements.txt",
        ".gitignore",
        ".env.example",
    ]:
        project_path = template_dir / "config" / project_file
        target_path = target / project_file
        write_utf8_file(target_path, read_text_template(project_path))

    config_data = {
        "default": {
            "project_name": project_name,
            "infra_project_name": default_project_prefix(),
        }
    }
    config_path = target / "scrapy_cffi.toml"
    with config_path.open("w", encoding="utf-8") as file_obj:
        toml.dump(config_data, file_obj)

    if is_demo:
        print(f"Demo project '{project_name}' created at {target}")
        print(f"  cd {project_name}")
    else:
        print(f"Project '{project_name}' created.")
        print(f"\tcd {project_name}")
        print(f"\tscrapy-cffi genspider <spider_name> <domain>")
        print("\tprofiles/ - optional self-built curl runtime layout reference")
