from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scrapy_cffi.mq.rabbitmq import RabbitMQManager  # noqa: E402


def amqp_single_url() -> str:
    return os.environ.get("SCRAPY_CFFI_AMQP_URL", "amqp://guest:guest@127.0.0.1:5672/")


def amqp_cluster_urls() -> List[str]:
    raw = os.environ.get("SCRAPY_CFFI_AMQP_CLUSTER", "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return [
        "amqp://guest:guest@127.0.0.1:5672/",
        "amqp://guest:guest@127.0.0.1:5673/",
        "amqp://guest:guest@127.0.0.1:5674/",
    ]


def exchange_name() -> str:
    return os.environ.get("SCRAPY_CFFI_AMQP_EXCHANGE", "scrapy_cffi")


async def run_queue_crud(manager: RabbitMQManager, queue_name: str) -> None:
    await manager.connect()
    queue = await manager.declare_queue(queue_name)

    # Create
    await manager.rpush(queue_name, b'{"op":"create","id":"1","value":"v1"}')
    created = await manager.dequeue_request(queue_name, timeout=3)
    assert created and b'"create"' in created, f"Create failed: {created!r}"

    # Read
    await manager.rpush(queue_name, b'{"op":"read","id":"1"}')
    read_msg = await manager.dequeue_request(queue_name, timeout=3)
    assert read_msg and b'"read"' in read_msg, f"Read failed: {read_msg!r}"

    # Update
    await manager.rpush(queue_name, b'{"op":"update","id":"1","value":"v2"}')
    updated = await manager.dequeue_request(queue_name, timeout=3)
    assert updated and b'"update"' in updated, f"Update failed: {updated!r}"

    # Delete (queue-level cleanup for broker integration tests)
    await queue.delete(if_unused=False, if_empty=False)
    await manager.close()
    print("crud ok")


async def test_single() -> None:
    manager = RabbitMQManager(
        stop_event=asyncio.Event(),
        rabbitmq_url=amqp_single_url(),
        exchange_name=exchange_name(),
        persist=True,
    )
    await run_queue_crud(manager, "broker.rabbit.single")


async def test_cluster() -> None:
    manager = RabbitMQManager(
        stop_event=asyncio.Event(),
        rabbitmq_url=amqp_cluster_urls(),
        exchange_name=exchange_name(),
        persist=True,
    )
    await run_queue_crud(manager, "broker.rabbit.cluster")


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="RabbitMQ broker tests")
    parser.add_argument("mode", nargs="?", default="single", choices=("single", "cluster", "all"))
    args = parser.parse_args(argv)

    async def run() -> None:
        if args.mode == "single":
            await test_single()
        elif args.mode == "cluster":
            await test_cluster()
        else:
            await test_single()
            await test_cluster()

    asyncio.run(run())


if __name__ == "__main__":
    main()
