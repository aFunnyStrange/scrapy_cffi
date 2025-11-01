import os
import platform
import asyncio
from curl_cffi import requests
from typing import List

try:
    import psutil
except ImportError as e:
    raise ImportError(
        "Missing psutil dependencies. "
        "Please install: pip install psutil"
    ) from e

class FDUtil:
    """Cross-platform file descriptor / handle utility class"""

    @staticmethod
    def get_max_fd():
        """
        Get the maximum number of files/handles that the current process can open.
        Windows: CRT _getmaxstdio
        Linux/macOS: resource.RLIMIT_NOFILE
        """
        if platform.system() == "Windows":
            import ctypes
            msvcrt = ctypes.cdll.msvcrt
            if hasattr(msvcrt, "_getmaxstdio"):
                return msvcrt._getmaxstdio()
            else:
                # Return default heuristic value
                return 512
        else:
            import resource
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            return soft

    @staticmethod
    def get_used_fd():
        """
        Get the number of file descriptors / handles currently used by the process.
        Windows: psutil.Process().num_handles()
        Linux/macOS: len(/proc/self/fd)
        """
        if platform.system() == "Windows":
            if psutil is None:
                raise RuntimeError("psutil is required on Windows to get used handles")
            p = psutil.Process()
            return p.num_handles()
        else:
            try:
                return len(os.listdir(f"/proc/self/fd"))
            except Exception:
                # Fallback: /proc folder not available, cannot determine
                return -1

    @staticmethod
    def print_fd_info():
        """Print the current process's max FD and used FD count"""
        max_fd = FDUtil.get_max_fd()
        used_fd = FDUtil.get_used_fd()
        print(f"[FDUtil] Max FD: {max_fd}, Used FD: {used_fd}")

async def measure_connection_memory(url="http://127.0.0.1:8002", test_connections=50):
    process = psutil.Process()
    mem_before = process.memory_info().rss

    sessions: List[requests.AsyncSession] = []
    for _ in range(test_connections):
        s = requests.AsyncSession()
        sessions.append(s)
        await s.get(url)

    mem_after = process.memory_info().rss
    per_connection_bytes = (mem_after - mem_before) / test_connections
    available_mem = psutil.virtual_memory().available
    safety_factor = 0.3
    safe_connections = int((available_mem * safety_factor) / per_connection_bytes)

    for s in sessions:
        await s.close()

    return per_connection_bytes, safe_connections

if __name__ == "__main__":
    FDUtil.print_fd_info()

    if platform.system().startswith("win"):
        # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    per_conn, safe_max = asyncio.run(measure_connection_memory())
    print(f"[Estimate] Each connection approx: {per_conn/1024:.2f} KB")
    print(f"[Estimate] Safe max concurrent connections: {safe_max}")