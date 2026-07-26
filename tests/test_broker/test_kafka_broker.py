from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Union

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scrapy_cffi.mq.kafka import KafkaManager  # noqa: E402


def kafka_single_bootstrap() -> str:
    return os.environ.get("SCRAPY_CFFI_KAFKA", "127.0.0.1:9092")


def kafka_cluster_bootstrap() -> List[str]:
    raw = os.environ.get("SCRAPY_CFFI_KAFKA_CLUSTER", "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return ["127.0.0.1:9094", "127.0.0.1:9095", "127.0.0.1:9096"]


async def run_kafka_flow(bootstrap: Union[str, List[str]], replication_factor: int) -> None:
    topic = "broker_crud_topic"
    group = f"broker-crud-{int(time.time() * 1000)}"
    done_event = asyncio.Event()
    stop_event = asyncio.Event()
    received: List[str] = []

    manager = KafkaManager(
        stop_event=stop_event,
        kafka_url=bootstrap,
        consumer_group=group,
    )
    await manager.connect()
    await manager.ensure_topic(topic, num_partitions=3, replication_factor=replication_factor)

    async def on_message(msg: bytes) -> None:
        received.append(msg.decode("utf-8"))
        if len(received) >= 4:
            done_event.set()

    await manager.register_consumer(topic, on_message, auto_offset_reset="earliest")
    await asyncio.sleep(0.8)

    # Event-driven CRUD semantics for append-only logs
    for op in ("create", "read", "update", "delete"):
        payload = f'{{"op":"{op}","id":"1"}}'.encode("utf-8")
        await manager.produce(topic, payload)

    await asyncio.wait_for(done_event.wait(), timeout=20)
    assert any('"create"' in m for m in received), f"Create event missing: {received!r}"
    assert any('"read"' in m for m in received), f"Read event missing: {received!r}"
    assert any('"update"' in m for m in received), f"Update event missing: {received!r}"
    assert any('"delete"' in m for m in received), f"Delete event missing: {received!r}"

    stop_event.set()
    await manager.delete_topics([topic])
    await manager.close()
    print("crud events ok")


async def run_request_queue_flow(bootstrap: Union[str, List[str]], replication_factor: int) -> None:
    topic = f"scheduler_requests_{int(time.time() * 1000)}"
    group = f"scheduler-workers-{int(time.time() * 1000)}"

    manager = KafkaManager(asyncio.Event(), bootstrap, consumer_group=group)
    await manager.connect()
    await manager.ensure_topic(topic, num_partitions=1, replication_factor=replication_factor)
    await manager.produce(topic, b"request-1")
    await manager.produce(topic, b"request-2")
    first = await manager.dequeue_request(topic, group, timeout=10)
    second = await manager.dequeue_request(topic, group, timeout=10)
    assert first and second
    assert [first.value, second.value] == [b"request-1", b"request-2"]

    # Completing a later offset must not commit across the earlier lease.
    await manager.ack_request(second)
    await manager.close()

    replay = KafkaManager(asyncio.Event(), bootstrap, consumer_group=group)
    replay_first = await replay.dequeue_request(topic, group, timeout=10)
    replay_second = await replay.dequeue_request(topic, group, timeout=10)
    assert replay_first and replay_second
    assert [replay_first.value, replay_second.value] == [b"request-1", b"request-2"]
    await replay.ack_request(replay_second)
    await replay.ack_request(replay_first)
    await replay.close()

    drained = KafkaManager(asyncio.Event(), bootstrap, consumer_group=group)
    assert await drained.dequeue_request(topic, group, timeout=3) is None
    await drained.delete_topics([topic])
    await drained.close()
    print("request queue offsets ok")


async def run_single() -> None:
    await run_kafka_flow(kafka_single_bootstrap(), replication_factor=1)
    await run_request_queue_flow(kafka_single_bootstrap(), replication_factor=1)


async def run_cluster() -> None:
    await run_kafka_flow(kafka_cluster_bootstrap(), replication_factor=3)
    await run_request_queue_flow(kafka_cluster_bootstrap(), replication_factor=3)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Kafka broker tests")
    parser.add_argument("mode", nargs="?", default="single", choices=("single", "cluster", "all"))
    args = parser.parse_args(argv)

    async def run() -> None:
        if args.mode == "single":
            await run_single()
        elif args.mode == "cluster":
            await run_cluster()
        else:
            await run_single()
            await run_cluster()

    asyncio.run(run())


if __name__ == "__main__":
    main()
