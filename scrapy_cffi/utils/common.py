import math, secrets, importlib, importlib.util, sys, os, inspect, json, time, traceback, toml, blackboxprotobuf, gzip
from blackboxprotobuf.lib.payloads import grpc
import asyncio, threading, multiprocessing
from typing import Any, Callable, TYPE_CHECKING, Union, Dict, List, Optional, Awaitable, Tuple
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
    from ..models.api import SettingsInfo
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

def create_uniqueId():
    origin_array = [int(time.time()), math.floor(secrets.randbits(32) / 4294967296 * 4294967296)]
    value = (origin_array[0] << 32) + origin_array[1]
    if value >= 2**63:
        value -= 2**64
    return str(value)

class ProtobufFactory(object):
    @staticmethod
    def protobuf_encode(data: Dict, typedef: Dict) -> bytes:
        return blackboxprotobuf.encode_message(data, typedef)

    @staticmethod
    def protobuf_decode(data: bytes) -> Tuple[Dict, Dict]:
        data, typedef = blackboxprotobuf.decode_message(data)
        return data, typedef

    @staticmethod
    def encode_message_length(length: int) -> bytes:
        if not (0 <= length <= 0xFFFFFFFF):
            raise ValueError("Message length must be between 0 and 2^32-1")
        return length.to_bytes(4, byteorder="big")

    @staticmethod
    def decode_message_length(data: bytes) -> int:
        if len(data) != 4:
            raise ValueError("Expected 4 bytes for message length")
        return int.from_bytes(data, byteorder="big")

    @staticmethod
    def grpc_encode(data: Dict, typedef: Dict, is_gzip: bool=False) -> bytes:
        encode_data = ProtobufFactory.protobuf_encode(data, typedef)
        if is_gzip:
            encode_data = gzip.compress(encode_data)
            return bytes([1]) + ProtobufFactory.encode_message_length(len(encode_data)) + encode_data
        return bytes([0]) + ProtobufFactory.encode_message_length(len(encode_data)) + encode_data
    
    @staticmethod
    def grpc_stream_encode(data: List[Tuple[Dict, Dict]], is_gzip=False) -> bytes:
        stream_bytes = b""
        for data, typedef in data:
            encoded_msg = ProtobufFactory.grpc_encode(data, typedef, is_gzip)
            stream_bytes += encoded_msg
        return stream_bytes
        
    @staticmethod
    def grpc_decode(data: bytes) -> Union[Tuple[Dict, Dict], List[Tuple[Dict, Dict]]]:
        results = []
        offset = 0
        total_len = len(data)

        while offset < total_len:
            if total_len - offset < 5:
                raise ValueError("Incomplete grpc message header")

            compress_flag = data[offset]
            offset += 1

            msg_length_bytes = data[offset:offset+4]
            if len(msg_length_bytes) < 4:
                raise ValueError("Incomplete grpc message length")
            msg_length = ProtobufFactory.decode_message_length(msg_length_bytes)
            offset += 4

            if total_len - offset < msg_length:
                raise ValueError("Incomplete grpc message body")
            message_data = data[offset:offset+msg_length]
            offset += msg_length
            if compress_flag == 1:
                decompressed = gzip.decompress(message_data)
                decoded_data, typedef = ProtobufFactory.protobuf_decode(decompressed)
            else:
                decoded_data, typedef = ProtobufFactory.protobuf_decode(message_data)
            results.append((decoded_data, typedef))
        return results[0] if len(results) == 1 else results

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

# Start a new event loop in an async environment to run async code (this will occupy its own thread pool)
async def run_coroutine_in_new_loop(
    target: Union[Awaitable, Callable[..., Awaitable]],
    *args: Any,
    **kwargs: Any
) -> Any:
    def _runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if inspect.isawaitable(target):
                coro = target
            elif callable(target):
                coro = target(*args, **kwargs)
                if not inspect.isawaitable(coro):
                    raise TypeError("Callable must return a coroutine")
            else:
                raise TypeError("target must be coroutine or coroutine-function")
            task = loop.create_task(coro)
            result = loop.run_until_complete(task)
            return result
        finally:
            pending = asyncio.all_tasks(loop)
            for t in pending:
                t.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
    return await asyncio.to_thread(_runner)

# Start a new thread in an async environment to run async code
def run_coroutine_in_thread(
    target: Union[Awaitable, Callable[..., Awaitable]],
    *args: Any,
    **kwargs: Any
) -> asyncio.Future:
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def thread_worker():
        try:
            sub_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(sub_loop)
            if inspect.isawaitable(target):
                coro = target
            elif callable(target):
                coro = target(*args, **kwargs)
                if not inspect.isawaitable(coro):
                    raise TypeError("Callable must return a coroutine")
            else:
                raise TypeError("target must be coroutine or coroutine-function")
            
            result = sub_loop.run_until_complete(coro)
            loop.call_soon_threadsafe(future.set_result, result)
        except Exception as e:
            loop.call_soon_threadsafe(future.set_exception, e)
        finally:
            pending = asyncio.all_tasks(sub_loop)
            for task in pending:
                task.cancel()
            sub_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            sub_loop.close()

    threading.Thread(target=thread_worker, daemon=True).start()
    return future

# Start a new process in an async environment to run async code (suitable for Linux/macOS)
# On Windows, due to process startup issues, Ctrl+C to interrupt will likely hang
# To be compatible with Windows startup, process_entrypoint cannot be inside a class or closure
def process_entrypoint(func: Callable, kwargs: Dict, queue: Optional[multiprocessing.Queue]):
    def handle_exit(sig, frame):
        print(f"[Child Process] Received signal {sig}, preparing to exit")
        import sys
        sys.exit(0)

    import platform
    if platform.system() != 'Windows':
        import os, signal
        try:
            os.setpgrp()
        except Exception as e:
            print(f"[Child Process] Failed to set process group: {e}")
        signal.signal(signal.SIGTERM, handle_exit)
        signal.signal(signal.SIGINT, handle_exit)

    try:
        if asyncio.iscoroutinefunction(func):
            result = asyncio.run(func(**kwargs))
        else:
            result = func(**kwargs)
        if queue:
            queue.put((True, result))
    except Exception as e:
        print("Error: -----------------------------------------------------------------------------------------")
        if queue:
            queue.put((False, str(e)))
        else:
            print(f"[Detached Child Process Exception]: {e}")

class ProcessTaskManager:
    def __init__(self):
        import atexit
        self._procs: List[multiprocessing.Process] = []
        atexit.register(self.terminate_all)

    async def run(self, func: Callable, return_result=True, **kwargs):
        loop = asyncio.get_running_loop()
        if return_result:
            queue = multiprocessing.Queue()

            def start_proc():
                proc = multiprocessing.Process(
                    target=process_entrypoint,
                    args=(func, kwargs, queue)
                )
                proc.start()
                self._procs.append(proc)
                return proc, queue

            proc, queue = await loop.run_in_executor(None, start_proc)

            try:
                result = await loop.run_in_executor(None, queue.get)
                proc.join(timeout=3)
                if proc.is_alive():
                    proc.terminate()
                    proc.join()
                ok, val = result
                if ok:
                    return val
                raise RuntimeError(val)
            finally:
                if proc.is_alive():
                    proc.terminate()
                    proc.join()
        else:
            def start_detached():
                proc = multiprocessing.Process(
                    target=process_entrypoint,
                    args=(func, kwargs, None),
                    daemon=True
                )
                proc.start()
                self._procs.append(proc)

            await loop.run_in_executor(None, start_detached)

    def terminate_all(self):
        for proc in self._procs:
            if proc.is_alive():
                try:
                    proc.terminate()
                    proc.join(timeout=1)
                except Exception as e:
                    print(f"[Main Process] Failed to terminate child process: {e}")
        self._procs.clear()