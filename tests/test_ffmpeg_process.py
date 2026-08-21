"""Verify bounded, shell-free FFmpeg subprocess utility behavior."""

import asyncio
import os
import shutil
import sys

import pytest

from scrapy_cffi.utils.ffmpeg import (
    FFmpegProcessManager,
    FFmpegProcessState,
    FFmpegProcessTimeoutError,
)


def test_short_process_returns_bounded_result_and_callback_output():
    """Run one awaited process and expose its terminal state and output."""

    async def run() -> None:
        """Exercise the same async API used by a Spider callback."""
        chunks = []
        manager = FFmpegProcessManager(
            executable=sys.executable,
            stdout_limit=4,
        )
        result = await manager.run(
            "-c",
            "print('abcdef')",
            timeout=5,
            stdout_callback=chunks.append,
        )
        assert result.state == FFmpegProcessState.SUCCEEDED
        assert result.succeeded is True
        assert result.returncode == 0
        assert result.pid is not None
        assert result.stdout_tail == ("abcdef" + os.linesep).encode()[-4:]
        assert b"abcdef" in b"".join(chunks)
        assert manager.processes == ()
        await manager.close()

    asyncio.run(run())


def test_command_arguments_are_never_interpreted_by_a_shell():
    """Pass shell metacharacters as one literal child-process argument."""

    async def run() -> None:
        """Round-trip a hostile-looking value through structured argv."""
        payload = 'value; $(echo injected) & "quoted"'
        manager = FFmpegProcessManager(executable=sys.executable)
        result = await manager.run(
            "-c",
            "import sys; sys.stdout.write(sys.argv[1])",
            payload,
            timeout=5,
        )
        assert result.state == FFmpegProcessState.SUCCEEDED
        assert result.stdout_tail.decode() == payload
        await manager.close()

    asyncio.run(run())


def test_callback_failure_does_not_stop_pipe_drain():
    """Classify callback failure without leaving a verbose child blocked."""

    def fail_callback(chunk: bytes) -> None:
        """Raise once to exercise callback isolation from pipe draining."""
        raise RuntimeError("callback failed")

    async def run() -> None:
        """Emit more bytes than one pipe buffer after the callback fails."""
        manager = FFmpegProcessManager(
            executable=sys.executable,
            stderr_limit=512,
        )
        result = await manager.run(
            "-c",
            "import sys; [sys.stderr.write('x' * 4096) for _ in range(32)]",
            stderr_callback=fail_callback,
        )
        assert result.state == FFmpegProcessState.FAILED
        assert b"callback RuntimeError: callback failed" in result.stderr_tail
        await manager.close()

    asyncio.run(run())


def test_process_limit_keeps_later_work_queued_until_slot_release():
    """Limit live child processes without a persistent worker loop."""

    async def run() -> None:
        """Use child stdin as event-driven release evidence."""
        manager = FFmpegProcessManager(
            max_processes=1,
            executable=sys.executable,
        )
        command = ("-c", "import sys; sys.stdin.readline()")
        first = manager.create(*command)
        assert await first.wait_started() == FFmpegProcessState.RUNNING
        second = manager.create(*command)
        assert second.state == FFmpegProcessState.QUEUED
        assert manager.active_count == 1

        first_result = await first.stop()
        assert first_result.state == FFmpegProcessState.CANCELLED
        assert await second.wait_started() == FFmpegProcessState.RUNNING
        assert manager.active_count == 1
        second_result = await second.stop()
        assert second_result.state == FFmpegProcessState.CANCELLED
        assert manager.active_count == 0
        await manager.close()

    asyncio.run(run())


def test_queued_process_can_be_cancelled_without_spawning():
    """Cancel queued work before it acquires the only process slot."""

    async def run() -> None:
        """Keep one child active while cancelling its queued sibling."""
        manager = FFmpegProcessManager(
            max_processes=1,
            executable=sys.executable,
        )
        command = ("-c", "import sys; sys.stdin.readline()")
        active = manager.create(*command)
        await active.wait_started()
        queued = manager.create(*command)
        result = await queued.kill()
        assert result.state == FFmpegProcessState.KILLED
        assert result.pid is None
        assert active.state == FFmpegProcessState.RUNNING
        await active.stop()
        await manager.close()

    asyncio.run(run())


def test_running_process_can_be_forcefully_killed():
    """Classify explicit force termination independently from exit codes."""

    async def run() -> None:
        """Start a sleeping process and force its terminal event."""
        manager = FFmpegProcessManager(executable=sys.executable)
        handle = manager.create("-c", "import time; time.sleep(60)")
        await handle.wait_started()
        result = await handle.kill()
        assert result.state == FFmpegProcessState.KILLED
        assert result.returncode is not None
        assert manager.active_count == 0
        await manager.close()

    asyncio.run(run())


def test_run_timeout_stops_process_and_raises_typed_error():
    """Use timeout only as an external bound and report the affected task."""

    async def run() -> None:
        """Bound one intentionally non-terminating child invocation."""
        manager = FFmpegProcessManager(
            executable=sys.executable,
            graceful_timeout=0,
            terminate_timeout=0.2,
        )
        with pytest.raises(FFmpegProcessTimeoutError) as error:
            await manager.run(
                "-c",
                "import time; time.sleep(60)",
                timeout=0.1,
            )
        assert error.value.task_id
        assert manager.active_count == 0
        await manager.close()

    asyncio.run(run())


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not installed")
def test_real_ffmpeg_short_task():
    """Execute one real bounded FFmpeg filter task when the binary is present."""

    async def run() -> None:
        """Generate a tiny in-memory color stream without an output artifact."""
        manager = FFmpegProcessManager(max_processes=1)
        result = await manager.run(
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=16x16:d=0.1",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
            timeout=10,
        )
        assert result.state == FFmpegProcessState.SUCCEEDED
        await manager.close()

    asyncio.run(run())
