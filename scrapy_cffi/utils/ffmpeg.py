"""Run bounded FFmpeg subprocesses without integrating them into crawler scheduling."""

import asyncio
import inspect
import os
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import (
    Awaitable,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)


StreamCallback = Callable[[bytes], Union[None, Awaitable[None]]]


class FFmpegProcessState(str, Enum):
    """Describe the in-memory lifecycle of one submitted subprocess."""

    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    KILLED = "killed"

    @property
    def is_terminal(self) -> bool:
        """Return whether no further state transition is expected."""
        return self in {
            self.SUCCEEDED,
            self.FAILED,
            self.CANCELLED,
            self.KILLED,
        }


@dataclass(frozen=True)
class FFmpegResult:
    """Return the bounded output and terminal facts of one subprocess."""

    task_id: str
    command: Tuple[str, ...]
    state: FFmpegProcessState
    returncode: Optional[int]
    pid: Optional[int]
    stdout_tail: bytes
    stderr_tail: bytes
    started_at: Optional[float]
    ended_at: float

    @property
    def succeeded(self) -> bool:
        """Return whether the process exited normally with code zero."""
        return self.state == FFmpegProcessState.SUCCEEDED


class FFmpegProcessError(RuntimeError):
    """Report invalid process configuration or unsupported runtime behavior."""


class FFmpegProcessTimeoutError(FFmpegProcessError):
    """Report a bounded run that exceeded its caller-provided safety limit."""

    def __init__(self, task_id: str, timeout: float) -> None:
        """Store the timed-out task identity and configured safety bound."""
        self.task_id = task_id
        self.timeout = timeout
        super().__init__(
            "FFmpeg task %s exceeded the %.3f second safety limit"
            % (task_id, timeout)
        )


class _TailBuffer:
    """Retain only the newest bounded bytes from a subprocess stream."""

    def __init__(self, limit: int) -> None:
        """Initialize one buffer with a non-negative byte limit."""
        self._limit = limit
        self._data = bytearray()

    def append(self, chunk: bytes) -> None:
        """Append a chunk while discarding bytes older than the limit."""
        if self._limit == 0:
            return
        self._data.extend(chunk)
        overflow = len(self._data) - self._limit
        if overflow > 0:
            del self._data[:overflow]

    def value(self) -> bytes:
        """Return an immutable snapshot of the retained tail."""
        return bytes(self._data)


class FFmpegProcess:
    """Expose one submitted process without leaking asyncio subprocess internals."""

    def __init__(
        self,
        manager: "FFmpegProcessManager",
        task_id: str,
        command: Tuple[str, ...],
    ) -> None:
        """Create a queued handle owned by one process manager."""
        loop = asyncio.get_running_loop()
        self.task_id = task_id
        self.command = command
        self.state = FFmpegProcessState.QUEUED
        self.returncode: Optional[int] = None
        self.pid: Optional[int] = None
        self.started_at: Optional[float] = None
        self.ended_at: Optional[float] = None
        self._manager = manager
        self._process: Optional[asyncio.subprocess.Process] = None
        self._runner_task: Optional[asyncio.Task] = None
        self._completion: asyncio.Future = loop.create_future()
        self._started_event = asyncio.Event()
        self._stop_requested = False
        self._force_kill_requested = False

    async def wait_started(self) -> FFmpegProcessState:
        """Wait until process creation succeeds, fails, or is cancelled."""
        await self._started_event.wait()
        return self.state

    async def wait(self) -> FFmpegResult:
        """Wait for the terminal result without transferring task ownership."""
        return await asyncio.shield(self._completion)

    async def stop(
        self,
        graceful_timeout: Optional[float] = None,
    ) -> FFmpegResult:
        """Request graceful FFmpeg shutdown, then terminate if it stays alive."""
        return await self._manager.stop(self, graceful_timeout=graceful_timeout)

    async def kill(self) -> FFmpegResult:
        """Forcefully stop the process or cancel it before process creation."""
        return await self._manager.kill(self)


class FFmpegProcessManager:
    """Create and own a bounded set of local FFmpeg subprocesses.

    The manager has no worker loop and creates no process until ``create`` or
    ``run`` is called. It is suitable for short awaited crawler work and as a
    reusable owner for longer processes explicitly managed by an application
    entrypoint such as a generated ``runner.py``.
    """

    def __init__(
        self,
        max_processes: Optional[int] = 2,
        executable: Union[str, os.PathLike] = "ffmpeg",
        graceful_timeout: float = 3.0,
        terminate_timeout: float = 2.0,
        stdout_limit: int = 64 * 1024,
        stderr_limit: int = 64 * 1024,
    ) -> None:
        """Configure process limits, executable selection, and bounded output."""
        if max_processes is not None and max_processes <= 0:
            raise ValueError("max_processes must be positive or None")
        if graceful_timeout < 0 or terminate_timeout < 0:
            raise ValueError("process stop timeouts must be non-negative")
        if stdout_limit < 0 or stderr_limit < 0:
            raise ValueError("stream tail limits must be non-negative")
        self.max_processes = max_processes
        self.executable = os.fspath(executable)
        self.graceful_timeout = graceful_timeout
        self.terminate_timeout = terminate_timeout
        self.stdout_limit = stdout_limit
        self.stderr_limit = stderr_limit
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._processes: Dict[str, FFmpegProcess] = {}
        self._closed = False

    @classmethod
    def from_settings(cls, settings: object, **kwargs: object) -> "FFmpegProcessManager":
        """Build a lazy manager from framework settings without starting FFmpeg."""
        return cls(
            max_processes=getattr(settings, "FFMPEG_MAX_PROCESSES"),
            executable=getattr(settings, "FFMPEG_EXECUTABLE"),
            **kwargs,
        )

    @property
    def processes(self) -> Tuple[FFmpegProcess, ...]:
        """Return a stable snapshot of queued and active handles."""
        return tuple(self._processes.values())

    @property
    def active_count(self) -> int:
        """Return the number of OS processes that are currently alive."""
        return sum(
            1
            for handle in self._processes.values()
            if handle._process is not None
            and handle._process.returncode is None
        )

    def create(
        self,
        *args: Union[str, os.PathLike],
        input_data: Optional[bytes] = None,
        cwd: Optional[Union[str, os.PathLike]] = None,
        env: Optional[Mapping[str, str]] = None,
        stdout_callback: Optional[StreamCallback] = None,
        stderr_callback: Optional[StreamCallback] = None,
    ) -> FFmpegProcess:
        """Submit one process and immediately return its in-memory handle."""
        loop = self._bind_running_loop()
        if self._closed:
            raise FFmpegProcessError("FFmpegProcessManager is closed")
        command = (self.executable,) + tuple(os.fspath(arg) for arg in args)
        task_id = uuid.uuid4().hex
        handle = FFmpegProcess(self, task_id, command)
        self._processes[task_id] = handle
        handle._runner_task = loop.create_task(
            self._execute(
                handle,
                input_data=input_data,
                cwd=cwd,
                env=env,
                stdout_callback=stdout_callback,
                stderr_callback=stderr_callback,
            ),
            name="ffmpeg:%s" % task_id,
        )
        return handle

    async def run(
        self,
        *args: Union[str, os.PathLike],
        timeout: Optional[float] = None,
        input_data: Optional[bytes] = None,
        cwd: Optional[Union[str, os.PathLike]] = None,
        env: Optional[Mapping[str, str]] = None,
        stdout_callback: Optional[StreamCallback] = None,
        stderr_callback: Optional[StreamCallback] = None,
    ) -> FFmpegResult:
        """Run one bounded subprocess and optionally enforce a safety timeout."""
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive or None")
        handle = self.create(
            *args,
            input_data=input_data,
            cwd=cwd,
            env=env,
            stdout_callback=stdout_callback,
            stderr_callback=stderr_callback,
        )
        if timeout is None:
            return await handle.wait()
        try:
            return await asyncio.wait_for(handle.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            await handle.stop()
            raise FFmpegProcessTimeoutError(handle.task_id, timeout) from exc

    async def stop(
        self,
        handle: FFmpegProcess,
        graceful_timeout: Optional[float] = None,
    ) -> FFmpegResult:
        """Stop one owned process, preferring FFmpeg's stdin quit command."""
        self._require_owned(handle)
        if graceful_timeout is not None and graceful_timeout < 0:
            raise ValueError("graceful_timeout must be non-negative")
        if handle.state.is_terminal:
            return await handle.wait()
        handle._stop_requested = True
        process = handle._process
        if process is None:
            if (
                handle.state == FFmpegProcessState.QUEUED
                and handle._runner_task is not None
            ):
                handle._runner_task.cancel()
                self._complete_cancelled(
                    handle,
                    _TailBuffer(self.stdout_limit),
                    _TailBuffer(self.stderr_limit),
                )
                return await handle.wait()
            await handle.wait_started()
            if handle.state.is_terminal:
                return await handle.wait()
            return await self.stop(
                handle,
                graceful_timeout=graceful_timeout,
            )

        handle.state = FFmpegProcessState.STOPPING
        await self._request_ffmpeg_quit(process)
        grace = self.graceful_timeout if graceful_timeout is None else graceful_timeout
        if await self._wait_process(process, grace):
            return await handle.wait()

        self._terminate_process(process)
        if not await self._wait_process(process, self.terminate_timeout):
            handle._force_kill_requested = True
            self._kill_process(process)
        return await handle.wait()

    async def kill(self, handle: FFmpegProcess) -> FFmpegResult:
        """Forcefully terminate one owned process or cancel queued creation."""
        self._require_owned(handle)
        if handle.state.is_terminal:
            return await handle.wait()
        handle._stop_requested = True
        handle._force_kill_requested = True
        process = handle._process
        if process is None:
            if (
                handle.state == FFmpegProcessState.QUEUED
                and handle._runner_task is not None
            ):
                handle._runner_task.cancel()
                self._complete_cancelled(
                    handle,
                    _TailBuffer(self.stdout_limit),
                    _TailBuffer(self.stderr_limit),
                )
                return await handle.wait()
            await handle.wait_started()
            if handle.state.is_terminal:
                return await handle.wait()
            return await self.kill(handle)
        handle.state = FFmpegProcessState.STOPPING
        self._kill_process(process)
        return await handle.wait()

    async def close(self) -> None:
        """Reject new work and stop every queued or running owned process."""
        if self._closed:
            return
        self._closed = True
        handles = [
            handle for handle in self._processes.values()
            if not handle.state.is_terminal
        ]
        if handles:
            await asyncio.gather(
                *(self.stop(handle) for handle in handles),
                return_exceptions=False,
            )

    async def __aenter__(self) -> "FFmpegProcessManager":
        """Return this lazily initialized process owner."""
        self._bind_running_loop()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        """Stop every process owned by this context."""
        await self.close()

    def _bind_running_loop(self) -> asyncio.AbstractEventLoop:
        """Bind lazily so Python 3.9 can construct the manager synchronously."""
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
            if self.max_processes is not None:
                self._semaphore = asyncio.Semaphore(self.max_processes)
        elif self._loop is not loop:
            raise FFmpegProcessError(
                "FFmpegProcessManager cannot be shared across event loops"
            )
        return loop

    async def _execute(
        self,
        handle: FFmpegProcess,
        input_data: Optional[bytes],
        cwd: Optional[Union[str, os.PathLike]],
        env: Optional[Mapping[str, str]],
        stdout_callback: Optional[StreamCallback],
        stderr_callback: Optional[StreamCallback],
    ) -> None:
        """Acquire one slot, create the process, drain streams, and settle state."""
        acquired = False
        stdout_buffer = _TailBuffer(self.stdout_limit)
        stderr_buffer = _TailBuffer(self.stderr_limit)
        stream_tasks: List[asyncio.Task] = []
        callback_errors: List[Exception] = []
        try:
            if self._semaphore is not None:
                await self._semaphore.acquire()
                acquired = True
            if handle._stop_requested:
                self._complete_cancelled(handle, stdout_buffer, stderr_buffer)
                return

            handle.state = FFmpegProcessState.STARTING
            kwargs = self._subprocess_kwargs(cwd=cwd, env=env)
            try:
                process = await asyncio.create_subprocess_exec(
                    *handle.command,
                    **kwargs,
                )
            except NotImplementedError as exc:
                raise FFmpegProcessError(
                    "asyncio subprocesses on Windows require ProactorEventLoop"
                ) from exc
            handle._process = process
            handle.pid = process.pid
            handle.started_at = time.time()
            handle.state = FFmpegProcessState.RUNNING
            handle._started_event.set()

            stream_tasks = [
                asyncio.create_task(
                    self._drain_stream(
                        process.stdout,
                        stdout_buffer,
                        stdout_callback,
                        callback_errors,
                    )
                ),
                asyncio.create_task(
                    self._drain_stream(
                        process.stderr,
                        stderr_buffer,
                        stderr_callback,
                        callback_errors,
                    )
                ),
            ]
            if input_data is not None and process.stdin is not None:
                process.stdin.write(input_data)
                await process.stdin.drain()
                process.stdin.close()
                if hasattr(process.stdin, "wait_closed"):
                    try:
                        await process.stdin.wait_closed()
                    except (BrokenPipeError, ConnectionResetError):
                        pass

            handle.returncode = await process.wait()
            await asyncio.gather(*stream_tasks)
            terminal_state = self._terminal_state(handle)
            if callback_errors and not handle._stop_requested:
                callback_error = callback_errors[0]
                stderr_buffer.append(
                    (
                        "callback %s: %s"
                        % (type(callback_error).__name__, callback_error)
                    ).encode()
                )
                terminal_state = FFmpegProcessState.FAILED
            self._complete(
                handle,
                terminal_state,
                stdout_buffer,
                stderr_buffer,
            )
        except asyncio.CancelledError:
            if handle._process is not None and handle._process.returncode is None:
                handle._force_kill_requested = True
                self._kill_process(handle._process)
                await handle._process.wait()
            self._complete_cancelled(handle, stdout_buffer, stderr_buffer)
        except Exception as exc:
            stderr_buffer.append(("%s: %s" % (type(exc).__name__, exc)).encode())
            self._complete(
                handle,
                FFmpegProcessState.FAILED,
                stdout_buffer,
                stderr_buffer,
            )
        finally:
            if stream_tasks:
                await asyncio.gather(*stream_tasks, return_exceptions=True)
            if acquired and self._semaphore is not None:
                self._semaphore.release()

    def _subprocess_kwargs(
        self,
        cwd: Optional[Union[str, os.PathLike]],
        env: Optional[Mapping[str, str]],
    ) -> Dict[str, object]:
        """Build shell-free platform-specific subprocess creation options."""
        kwargs: Dict[str, object] = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }
        if cwd is not None:
            kwargs["cwd"] = os.fspath(cwd)
        if env is not None:
            kwargs["env"] = dict(env)
        if os.name == "nt":
            kwargs["creationflags"] = getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0,
            )
        else:
            kwargs["start_new_session"] = True
        return kwargs

    async def _drain_stream(
        self,
        stream: Optional[asyncio.StreamReader],
        buffer: _TailBuffer,
        callback: Optional[StreamCallback],
        callback_errors: List[Exception],
    ) -> None:
        """Drain one pipe continuously to avoid child-process deadlocks."""
        if stream is None:
            return
        while True:
            chunk = await stream.read(16 * 1024)
            if not chunk:
                return
            buffer.append(chunk)
            if callback is not None:
                try:
                    callback_result = callback(chunk)
                    if inspect.isawaitable(callback_result):
                        await callback_result
                except Exception as exc:
                    callback_errors.append(exc)
                    callback = None

    async def _request_ffmpeg_quit(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        """Ask FFmpeg to finalize its output through its stdin command API."""
        if process.returncode is not None or process.stdin is None:
            return
        try:
            process.stdin.write(b"q\n")
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, RuntimeError):
            return

    async def _wait_process(
        self,
        process: asyncio.subprocess.Process,
        timeout: float,
    ) -> bool:
        """Wait within an external safety bound without inferring completion."""
        if process.returncode is not None:
            return True
        try:
            await asyncio.wait_for(asyncio.shield(process.wait()), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def _terminate_process(self, process: asyncio.subprocess.Process) -> None:
        """Request platform-appropriate process-group termination."""
        if process.returncode is not None:
            return
        if os.name == "nt":
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
                return
            except (AttributeError, OSError, ProcessLookupError):
                process.terminate()
                return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

    def _kill_process(self, process: asyncio.subprocess.Process) -> None:
        """Forcefully terminate the direct Windows process or POSIX group."""
        if process.returncode is not None:
            return
        if os.name == "nt":
            try:
                process.kill()
            except ProcessLookupError:
                return
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return

    def _terminal_state(self, handle: FFmpegProcess) -> FFmpegProcessState:
        """Classify an observed exit using explicit caller stop intent."""
        if handle._force_kill_requested:
            return FFmpegProcessState.KILLED
        if handle._stop_requested:
            return FFmpegProcessState.CANCELLED
        if handle.returncode == 0:
            return FFmpegProcessState.SUCCEEDED
        return FFmpegProcessState.FAILED

    def _complete_cancelled(
        self,
        handle: FFmpegProcess,
        stdout_buffer: _TailBuffer,
        stderr_buffer: _TailBuffer,
    ) -> None:
        """Settle a queued or internally cancelled handle exactly once."""
        state = (
            FFmpegProcessState.KILLED
            if handle._force_kill_requested
            else FFmpegProcessState.CANCELLED
        )
        self._complete(handle, state, stdout_buffer, stderr_buffer)

    def _complete(
        self,
        handle: FFmpegProcess,
        state: FFmpegProcessState,
        stdout_buffer: _TailBuffer,
        stderr_buffer: _TailBuffer,
    ) -> None:
        """Publish one immutable terminal result and release manager tracking."""
        if handle._completion.done():
            return
        if handle._process is not None:
            handle.returncode = handle._process.returncode
        handle.state = state
        handle.ended_at = time.time()
        handle._started_event.set()
        result = FFmpegResult(
            task_id=handle.task_id,
            command=handle.command,
            state=state,
            returncode=handle.returncode,
            pid=handle.pid,
            stdout_tail=stdout_buffer.value(),
            stderr_tail=stderr_buffer.value(),
            started_at=handle.started_at,
            ended_at=handle.ended_at,
        )
        handle._completion.set_result(result)
        self._processes.pop(handle.task_id, None)

    def _require_owned(self, handle: FFmpegProcess) -> None:
        """Reject handles created by another manager."""
        if handle._manager is not self:
            raise FFmpegProcessError("process handle belongs to another manager")


__all__ = [
    "FFmpegProcess",
    "FFmpegProcessError",
    "FFmpegProcessManager",
    "FFmpegProcessState",
    "FFmpegProcessTimeoutError",
    "FFmpegResult",
    "StreamCallback",
]
