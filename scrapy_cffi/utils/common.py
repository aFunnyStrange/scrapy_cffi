import importlib, importlib.util, sys, os, inspect, json, traceback, toml
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Callable, TYPE_CHECKING, Union, Dict, List, Optional, Type
if TYPE_CHECKING:
    from logging import Logger

def get_run_py_dir():
    from pathlib import Path
    return Path(sys.argv[0]).resolve().parent

def setup_uvloop_once():
    if getattr(setup_uvloop_once, "_done", False):
        return
    try:
        if sys.platform != "win32":
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            print("uvloop enabled")
        else:
            print("uvloop not available on Windows")
    except ImportError:
        print("uvloop not installed")
    finally:
        setup_uvloop_once._done = True

def async_context_factory(
    max_tasks: Optional[int] = None,
    semaphore_cls: Union[Type[asyncio.Semaphore], None] = None
):
    if max_tasks is None:
        @asynccontextmanager
        async def empty_context():
            yield
        return empty_context
    else:
        sem_cls = semaphore_cls or asyncio.BoundedSemaphore
        sem = sem_cls(max_tasks)

        @asynccontextmanager
        async def sem_context():
            async with sem:
                yield
        return sem_context

class ResultHolder:
    def __init__(self):
        self._future = asyncio.get_event_loop().create_future()

    def set_result(self, value):
        if not self._future.done():
            self._future.set_result(value)

    async def get_result(self):
        return await self._future

async def cancel_all_tasks(timeout: float = 5.0):
    current_task = asyncio.current_task()
    all_tasks = asyncio.all_tasks()
    cancel_targets = [t for t in all_tasks if t is not current_task and not t.done()]
    print(f"[cancel] Found {len(cancel_targets)} tasks to cancel")
    for task in cancel_targets:
        task.cancel()

    await asyncio.sleep(0)

    try:
        await asyncio.wait(cancel_targets, timeout=timeout)
    except Exception as e:
        print(f"[cancel] Error while waiting for task cancellation: {e}")

    still_pending = [t for t in cancel_targets if not t.done()]
    if still_pending:
        print(f"[cancel] {len(still_pending)} tasks were not cancelled within {timeout}s, calling os._exit(0) for forced termination")
        for task in still_pending:
            print(f"\n--- Incomplete task: {task.get_name()} ---")
            for frame in task.get_stack():
                print("".join(traceback.format_stack(f=frame)))
        await asyncio.sleep(1)
        os._exit(0)
    else:
        print(f"[cancel] All tasks successfully cancelled within {timeout}s")

    for task in cancel_targets:
        try:
            await asyncio.wait_for(task, timeout=1)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            pass

# Dynamically import class by its full path and return the class object
def load_object(path: str, base_module: str = None):
    if not path:
        raise ValueError("Empty path is not allowed")

    if '.' not in path:
        # Short class name, try loading from base_module or caller's module
        if base_module:
            module = importlib.import_module(base_module)
        else:
            # Get caller's module (2nd frame on the stack)
            frame = sys._getframe(1)
            caller_globals = frame.f_globals
            module_name = caller_globals.get('__name__', '__main__')
            module = sys.modules[module_name]
        try:
            return getattr(module, path)
        except AttributeError as e:
            raise AttributeError(f"Class '{path}' not found in module '{module.__name__}'") from e
    else:
        try:
            module_path, class_name = path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            return getattr(module, class_name)
        except (ImportError, AttributeError, ValueError) as e:
            raise ImportError(f"Cannot load '{path}': {e}") from e

# ——————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————
# Convert SettingsInfo (Pydantic model) to scrapy-style settings.py format
def to_scrapy_settings_py(settings_obj) -> str:
    from pydantic import BaseModel
    def serialize_value(value: Any) -> str:
        if isinstance(value, BaseModel):
            return json.dumps(value.model_dump(), indent=4, ensure_ascii=False)
        elif isinstance(value, dict):
            return json.dumps(value, indent=4, ensure_ascii=False)
        elif isinstance(value, (list, tuple)):
            return repr(value)
        elif isinstance(value, str):
            return repr(value)
        else:
            return str(value)

    lines = []
    for field_name, value in settings_obj.model_dump().items():
        if value is not None:
            line = f"{field_name} = {serialize_value(value)}"
            lines.append(line)
    return "\n".join(lines)

# Load settings from a given path (supports Python or JSON)
def load_settings_with_path(settings_path: str=""):
    from ..settings import SettingsInfo
    if settings_path == "":
        settings_path = str(get_run_py_dir() / "settings.py")
    if ".py" in settings_path:
        custom_settings = load_settings_from_py(settings_path)
    else:
        # Try parsing as JSON if not a Python file
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                custom_settings: Dict[str, Union[List, str, None]] = json.loads(f.read())
                custom_settings = {k.upper(): v for k, v in custom_settings.items()}
        except Exception as e:
            return f"Error parsing JSON config: {e}"
    return SettingsInfo(**custom_settings)

# Load settings from a Python file as a dictionary
def load_settings_from_py(filepath: str, auto_upper=True) -> Dict[str, Any]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Settings file not found: {filepath}")
    
    module_name = "__user_settings__"
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    settings = {
        (key.upper() if auto_upper else key): getattr(module, key)
        for key in dir(module)
        if not key.startswith("__")
    }
    return settings

# Convert a Python settings file to a .toml file
def convert_to_toml(py_path: str, toml_path: str):
    config = load_settings_from_py(py_path, auto_upper=False)
    toml_dict = {}
    for key, value in config.items():
        if isinstance(value, dict):
            toml_dict[key] = value
        else:
            toml_dict[key] = value
    with open(toml_path, "w", encoding="utf-8") as f:
        toml.dump(toml_dict, f)
    print(f"Converted {py_path} to {toml_path} successfully.")

# ——————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————
def get_class_name(item):
    cls = item if isinstance(item, type) else item.__class__
    return f"{cls.__module__}.{cls.__name__}"

# Get the spider class
def get_all_spiders_cls(spiders_dir: str):
    from ..spiders import BaseSpider
    if not os.path.isabs(spiders_dir):
        spiders_dir = os.path.join(get_run_py_dir(), spiders_dir)
    spider_classes = []
    for root, dirs, files in os.walk(spiders_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for file in files:
            if not file.endswith('.py'):
                continue
            if file.startswith('__') or file.startswith('test_'):
                continue

            full_path = os.path.join(root, file)
            module_name = os.path.splitext(os.path.relpath(full_path, spiders_dir))[0].replace(os.path.sep, '.')
            
            spec = importlib.util.spec_from_file_location(module_name, full_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for obj in vars(module).values():
                if inspect.isclass(obj) and issubclass(obj, BaseSpider) and obj.__module__ == module.__name__:
                    spider_classes.append(obj)
    return spider_classes

# Get all spider names
def get_all_spiders_name(logger: "Logger"=None, spiders_cls_list=None):
    spiders_name = [spider.name for spider in spiders_cls_list]
    logger.debug(f"all_spiders：{spiders_name}")
    return spiders_name
    
async def run_with_timeout(
    func: Callable[..., Any],
    *args,
    stop_event: asyncio.Event,
    timeout: float = 1.0,
    max_total_time: Optional[float] = None,
    **kwargs
) -> Any:
    is_async = inspect.iscoroutinefunction(func)
    start_time = asyncio.get_event_loop().time()

    while not stop_event.is_set():
        try:
            if is_async:
                task = asyncio.create_task(func(*args, **kwargs))
            else:
                task = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
            return await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            now = asyncio.get_event_loop().time()
            if max_total_time is not None and (now - start_time > max_total_time):
                raise asyncio.TimeoutError("Maximum total wait time exceeded")

            await asyncio.sleep(0.05)
        except BaseException as e:
            if stop_event.is_set():
                raise asyncio.CancelledError("Stopped by stop_event")
            raise
    raise asyncio.CancelledError("stop_event set during call")