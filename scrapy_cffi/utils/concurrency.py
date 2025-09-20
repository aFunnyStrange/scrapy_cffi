import asyncio, threading, multiprocessing, inspect
from multiprocessing.managers import BaseManager as _BaseManager
from typing import Any, Callable, Union, Dict, List, Optional, Awaitable

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

class ProcessManager:
    """
    A general-purpose multiprocessing manager.
    - Supports registering functions, objects, and classes.
    - Provides server and client startup/shutdown.
    """
    class _Manager(_BaseManager): pass

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 50000,
        authkey: str = "abc",
        register_methods: Union[Dict[str, Any], None] = None,
    ):
        """
        :param host: Server host
        :param port: Server port
        :param authkey: Authentication key
        :param register_methods:
            - dict: { "name": callable / class / object }  -> for server registration
            - list or str: ["name1", "name2"] / "name"   -> for client registration only (placeholders)
        """
        self.address = (host, port)
        self.authkey = authkey.encode("utf-8")
        self._manager = None

        if isinstance(register_methods, dict):
            self._register_methods = register_methods
        elif isinstance(register_methods, list):
            self._register_methods = {name: None for name in register_methods}
        elif isinstance(register_methods, str):
            self._register_methods = {register_methods: None}
        else:
            self._register_methods = {}

    def _do_register(self):
        """Register functions, objects, or classes"""
        for name, target in self._register_methods.items():
            if target is None:
                self._Manager.register(name)
            elif isinstance(target, type):
                self._Manager.register(name, target)
            elif not callable(target):
                self._Manager.register(name, callable=lambda obj=target: obj)
            else:
                self._Manager.register(name, callable=target)

    def start_server(self, run_mode: int = 1):
        """Start a server process (background) or blocking mode"""
        self._do_register()
        self._manager = self._Manager(address=self.address, authkey=self.authkey)
        print(f"[ProcessManager] Server started at {self.address}")

        if run_mode:  # background mode
            self._manager.start()
        else:         # blocking mode
            server = self._manager.get_server()
            server.serve_forever()

    def shutdown(self):
        """Shutdown the server"""
        if self._manager:
            self._manager.shutdown()
            print("[ProcessManager] Server shutdown")

    def start_client(self):
        """Start a client and connect to the server"""
        import os
        self._do_register()
        self._manager = self._Manager(address=self.address, authkey=self.authkey)
        self._manager.connect()
        print(f"[ProcessManager] pid:{os.getpid()}, Client Connected to {self.address}")

    def __getattr__(self, item):
        if self._manager and hasattr(self._manager, item):
            return getattr(self._manager, item)
        raise AttributeError(item)
    
class ThreadFuture:
    def __init__(self, func: Callable, *args, **kwargs):
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._result: Optional[Any] = None
        self._exception: Optional[Exception] = None
        self._done_event = threading.Event()
        self._callbacks: List[Callable[['ThreadFuture'], None]] = []

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self._result = self._func(*self._args, **self._kwargs)
        except Exception as e:
            self._exception = e
        finally:
            self._done_event.set()
            for callback in self._callbacks:
                try:
                    callback(self)
                except Exception:
                    pass

    def done(self) -> bool:
        return self._done_event.is_set()

    def result(self, timeout: float = None) -> Any:
        finished = self._done_event.wait(timeout)
        if not finished:
            raise TimeoutError("Task not finished yet")
        if self._exception:
            raise self._exception
        return self._result

    def add_done_callback(self, fn: Callable[['ThreadFuture'], None]):
        if self.done():
            fn(self)
        else:
            self._callbacks.append(fn)