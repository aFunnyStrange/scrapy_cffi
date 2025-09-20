import asyncio
from typing import List, Tuple, Dict
from scrapy_cffi.databases import RedisManager

async def test_redis_single():
    print("=== Testing SINGLE mode ===")
    stop_event = asyncio.Event()
    redis_url = "redis://localhost:6379/0"
    redis_manager = RedisManager(stop_event=stop_event, redis_url=redis_url, redis_mode="single")

    key_new_seen = "test_new_seen_single"
    key_is_req = "test_is_req_single"
    queue_key = "test_queue_single"
    fp = "req_single_001"
    req_bytes = b"request_data_single"

    await redis_manager.delete(key_new_seen, key_is_req, queue_key)

    res = await redis_manager.do_filter(fp, key_new_seen, key_is_req)
    if res:
        print("do_filter:", res)
        await redis_manager.lpush(queue_key, req_bytes)

        req = await redis_manager.dequeue_request(queue_key, decode_responses=True)
        print("dequeue_request:", req)

    await redis_manager.delete(key_new_seen, key_is_req, queue_key)
    print("SINGLE test done.\n")


async def test_redis_sentinel():
    print("=== Testing SENTINEL mode ===")
    stop_event = asyncio.Event()
    sentinel_hosts: List[Tuple[str, int]] = [("localhost", 26379), ("localhost", 26380), ("localhost", 26381)]
    master_name = "mymaster"

    redis_manager = RedisManager(
        stop_event=stop_event,
        redis_url=sentinel_hosts,
        redis_mode="sentinel",
        master_name=master_name
    )

    key_new_seen = "test_new_seen_sentinel"
    key_is_req = "test_is_req_sentinel"
    queue_key = "test_queue_sentinel"
    fp = "req_sentinel_001"
    req_bytes = b"request_data_sentinel"

    await redis_manager.delete(key_new_seen, key_is_req, queue_key)

    res = await redis_manager.do_filter(fp, req_bytes, key_new_seen, key_is_req, queue_key)
    print("do_filter:", res)

    req = await redis_manager.dequeue_request(queue_key, decode_responses=True)
    print("dequeue_request:", req)

    await redis_manager.delete(key_new_seen, key_is_req, queue_key)
    print("SENTINEL test done.\n")


async def test_redis_cluster():
    print("=== Testing CLUSTER mode ===")
    stop_event = asyncio.Event()
    cluster_nodes: List[Dict] = [
        {"host": "localhost", "port": 7000},
        {"host": "localhost", "port": 7001},
        {"host": "localhost", "port": 7002},
    ]

    redis_manager = RedisManager(
        stop_event=stop_event,
        redis_url=cluster_nodes,
        redis_mode="cluster"
    )

    key_new_seen = "test_new_seen_cluster"
    key_is_req = "test_is_req_cluster"
    queue_key = "test_queue_cluster"
    fp = "req_cluster_001"
    req_bytes = b"request_data_cluster"

    await redis_manager.delete(key_new_seen, key_is_req, queue_key)

    res = await redis_manager.do_filter(fp, req_bytes, key_new_seen, key_is_req, queue_key)
    print("do_filter:", res)

    req = await redis_manager.dequeue_request(queue_key, decode_responses=True)
    print("dequeue_request:", req)

    await redis_manager.delete(key_new_seen, key_is_req, queue_key)
    print("CLUSTER test done.\n")


async def main():
    await test_redis_single()
    await test_redis_sentinel()
    await test_redis_cluster()


if __name__ == "__main__":
    asyncio.run(main())
