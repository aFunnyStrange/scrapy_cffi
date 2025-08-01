import shutil, os
from pathlib import Path

def copytree_merge(src: Path, dst: Path):
    src = Path(src)
    dst = Path(dst)
    if not src.is_dir():
        raise ValueError(f"源路径不是目录: {src}")

    if not dst.exists():
        os.makedirs(dst)

    for item in src.iterdir():
        s = src / item.name
        d = dst / item.name
        if s.is_dir():
            copytree_merge(s, d)
        else:
            shutil.copy2(s, d)

def run(use_task: bool, use_redis: bool):
    base = Path(__file__).parent.parent # scrapy_cffi
    template_dir = base / "templates"
    target: Path = Path.cwd() / "demo"

    settings_path = target / "spiders" / "settings.py" if use_task else target / "settings.py"
    settings_code = settings_path.read_text(encoding='utf-8')
    settings_code = settings_code.replace('# settings.EXTENSIONS_PATH', 'settings.EXTENSIONS_PATH')
    settings_code = settings_code.replace('# settings.ITEM_PIPELINES_PATH', 'settings.ITEM_PIPELINES_PATH')
    settings_code = settings_code.replace('# "interceptors.CustomDownloadInterceptor1"', '"interceptors.CustomDownloadInterceptor1"')
    settings_code = settings_code.replace('# "interceptors.CustomDownloadInterceptor2"', '"interceptors.CustomDownloadInterceptor2"')
    settings_path.write_text(settings_code, encoding='utf-8')

    spider_dir = target / "spiders" / "spiders" if use_task else target / "spiders"
    demo_spiders_dir = template_dir / "demo_spider"
    
    # demo_server
    copytree_merge(template_dir / "server", target)
    readme_path = target / "readme.txt"
    readme_code = readme_path.read_text(encoding='utf-8')
    if use_task:
        readme_code = readme_code.replace('2.run runner.py', '2.run manager.py')
    if use_redis:
        readme_code = readme_code + '\n3.redis-cli\n4.RPUSH customRedisSpider_test http://127.0.0.1:8002\r\n'
    readme_path.write_text(readme_code, encoding='utf-8')

    if use_redis:
        from .base import find_project_root
        from .genspider import check_use_redis
        project_path = find_project_root(is_demo=True)
        use_task = check_use_redis(project_path, use_redis, use_task)
        copytree_merge(demo_spiders_dir, spider_dir)
        update_spiders_path(project_path=target, demo_spiders_dir=demo_spiders_dir, spider_dir=spider_dir, use_task=use_task, use_redis=use_redis)
        # runner.py update spider_path

        # module path with `spiders`
        spiders_dir = target / "spiders" if use_task else target
        runner_path = spiders_dir / "runner.py"
        runner_code = runner_path.read_text(encoding='utf-8')
        runner_code = runner_code.replace('crawler, engine_task = await advance_main()', '# crawler, engine_task = await advance_main()')
        runner_code = runner_code.replace('# crawler, engine_task = await advance_main_all()', 'crawler, engine_task = await advance_main_all()')
        runner_code = runner_code.replace('import threading', '# import threading')
        runner_code = runner_code.replace('t = threading.Thread(', '# t = threading.Thread(')
        runner_code = runner_code.replace('t.start()', '# t.start()')
        runner_code = runner_code.replace('t.join()', '# t.join()')
        runner_code = runner_code.replace(' main()', ' # main()')
        if use_task:
            runner_code = runner_code.replace('spider_path="spiders.CustomSpider"', 'spider_path="spiders.spiders.CustomSpider"')
            runner_code = runner_code.replace('get_run_py_dir() / "spiders"', 'get_run_py_dir() / "spiders" / "spiders"')
        runner_path.write_text(runner_code, encoding='utf-8')
    else:
        spider_dir.mkdir(parents=True, exist_ok=True)
        update_spiders_path(project_path=target, demo_spiders_dir=demo_spiders_dir, spider_dir=spider_dir, use_task=use_task, use_redis=use_redis)

    print(f"Project 'demo' with tasks manager created.") if use_task else print(f"Project 'demo' created.")

def update_spiders_path(project_path: Path, demo_spiders_dir: Path, spider_dir: Path, use_task: bool, use_redis: bool):
    spider_files = ["customSpider", "studentSpider"]
    for spider_name in spider_files:
        spider_path = demo_spiders_dir / f"{spider_name}.py"
        spider_code = spider_path.read_text('utf-8')

        write_path = spider_dir / f"{spider_name}.py"
        if use_task:
            spider_code = spider_code.replace("from items.item import CustomItem", "from spiders.items.item import CustomItem")
        write_path.write_text(spider_code, encoding='utf-8')
        cls_name = spider_name[0].upper() + spider_name[1:] if spider_name else spider_name
        if not use_redis:
            # update __init__.py
            from .genspider import update_spiders_init
            update_spiders_init(project_path=project_path, class_name=cls_name, spider_name=spider_name, use_task=use_task)