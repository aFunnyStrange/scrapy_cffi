from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scrapy_cffi.databases import RedisManager  # noqa: E402


def redis_single_url() -> str:
    return os.environ.get("SCRAPY_CFFI_REDIS_URL", "redis://127.0.0.1:6379/0")


def redis_sentinel_hosts() -> List[Tuple[str, int]]:
    host = os.environ.get("SCRAPY_CFFI_REDIS_SENTINEL_HOST", "127.0.0.1")
    ports = os.environ.get("SCRAPY_CFFI_REDIS_SENTINEL_PORTS", "26379,26380,26381")
    return [(host, int(p.strip())) for p in ports.split(",") if p.strip()]


def redis_sentinel_master_name() -> str:
    return os.environ.get("SCRAPY_CFFI_REDIS_MASTER_NAME", "mymaster")


def redis_sentinel_master_override() -> Tuple[str, int]:
    raw = os.environ.get("SCRAPY_CFFI_REDIS_MASTER_OVERRIDE", "127.0.0.1:6379")
    host, _, port = raw.partition(":")
    return (host, int(port or 6379))


def redis_cluster_nodes() -> List[str]:
    raw = os.environ.get("SCRAPY_CFFI_REDIS_CLUSTER_NODES", "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return [f"redis://127.0.0.1:{p}" for p in range(7000, 7006)]


async def run_crud(redis_manager: RedisManager, prefix: str) -> None:
    key = f"{prefix}:kv"
    queue_key = f"{prefix}:queue"

    await redis_manager.delete(key, queue_key)

    # Create
    await redis_manager.set(key, "v1")
    v = await redis_manager.get(key)
    assert v in ("v1", b"v1"), f"Create failed: {v!r}"

    # Read
    print("read:", v.decode() if isinstance(v, bytes) else v)

    # Update
    await redis_manager.set(key, "v2")
    v2 = await redis_manager.get(key)
    assert v2 in ("v2", b"v2"), f"Update failed: {v2!r}"

    # Queue flow check (framework scheduler-style)
    await redis_manager.lpush(queue_key, b"req-001")
    popped = await redis_manager.dequeue_request(queue_key, timeout=2, decode_responses=True)
    assert popped == "req-001", f"Queue read failed: {popped!r}"

    # Delete
    await redis_manager.delete(key, queue_key)
    gone = await redis_manager.get(key)
    assert gone is None, f"Delete failed: {gone!r}"
    print("crud ok")


async def run_single() -> None:
    manager = RedisManager(
        stop_event=asyncio.Event(),
        redis_url=redis_single_url(),
        redis_mode="single",
    )
    try:
        await run_crud(manager, "broker:redis:single")
    finally:
        if hasattr(manager, "aclose"):
            await manager.aclose()
        else:
            await manager.close()


async def run_sentinel() -> None:
    host, port = redis_sentinel_master_override()
    manager = RedisManager(
        stop_event=asyncio.Event(),
        redis_url=redis_sentinel_hosts(),
        redis_mode="sentinel",
        master_name=redis_sentinel_master_name(),
        sentinel_override_master=(host, port),
    )
    try:
        await run_crud(manager, "broker:redis:sentinel")
    finally:
        if hasattr(manager, "aclose"):
            await manager.aclose()
        else:
            await manager.close()


async def run_cluster() -> None:
    manager = RedisManager(
        stop_event=asyncio.Event(),
        redis_url=redis_cluster_nodes(),
        redis_mode="cluster",
    )
    try:
        await run_crud(manager, "broker:redis:cluster")
    finally:
        if hasattr(manager, "aclose"):
            await manager.aclose()
        else:
            await manager.close()


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Redis broker CRUD tests")
    parser.add_argument(
        "mode",
        nargs="?",
        default="single",
        choices=("single", "sentinel", "cluster", "all"),
    )
    args = parser.parse_args(argv)

    async def run() -> None:
        if args.mode == "single":
            await run_single()
        elif args.mode == "sentinel":
            await run_sentinel()
        elif args.mode == "cluster":
            await run_cluster()
        else:
            await run_single()
            await run_sentinel()
            await run_cluster()

    asyncio.run(run())


if __name__ == "__main__":
    main()
