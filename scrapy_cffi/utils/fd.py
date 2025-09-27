import os
import platform

try:
    import psutil
except ImportError as e:
    raise ImportError(
        "Missing scrapy dependencies. "
        "Please install: pip install scrapy"
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

if __name__ == "__main__":
    FDUtil.print_fd_info()