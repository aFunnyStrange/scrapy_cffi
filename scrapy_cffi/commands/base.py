from pathlib import Path

def find_project_root(start: Path = None, is_demo=False) -> Path:
    if start is None:
        start = Path.cwd()
    all_path = [start / "demo"] if is_demo else [start, *start.parents]
    for path in all_path:
        if (path / "scrapy_cffi.toml").exists():
            return path
    raise FileNotFoundError("Project root not found (missing scrapy_cffi.toml)")