"""Provide importable, picklable short tasks for the generated Demo."""

import os
import time


def double_in_worker(value: int) -> dict:
    """Return worker identity after a deliberately short blocking operation."""
    time.sleep(0.05)
    return {"pid": os.getpid(), "value": value * 2}


__all__ = ["double_in_worker"]
