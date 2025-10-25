import asyncio
from typing import List, Tuple
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
    master_host = "<PUBLIC_IP>"

    sentinel_hosts: List[Tuple[str, int]] = [(master_host, 26379), (master_host, 26380), (master_host, 26381)]
    master_name = "mymaster"

    redis_manager = RedisManager(
        stop_event=stop_event,
        redis_url=sentinel_hosts,
        redis_mode="sentinel",
        master_name=master_name,
        sentinel_override_master=(master_host, 6379)
    )

    key_new_seen = "test_new_seen_sentinel"
    key_is_req = "test_is_req_sentinel"
    queue_key = "test_queue_sentinel"
    fp = "req_sentinel_001"
    req_bytes = b"request_data_sentinel"

    await redis_manager.delete(key_new_seen, key_is_req, queue_key)

    res = await redis_manager.do_filter(fp, key_new_seen, key_is_req)
    print("do_filter:", res)

    if res:
        await redis_manager.lpush(queue_key, req_bytes)

    req = await redis_manager.dequeue_request(queue_key, decode_responses=True)
    print("dequeue_request:", req)

    await redis_manager.delete(key_new_seen, key_is_req, queue_key)
    print("SENTINEL test done.\n")


async def test_redis_cluster():
    print("=== Testing CLUSTER mode ===")
    stop_event = asyncio.Event()
    master_host = "<PUBLIC_IP>"
    from urllib.parse import urlparse
    cluster_nodes = [f"redis://{master_host}:{i}" for i in range(7000, 7006)]
    startup_nodes = [{"host": urlparse(u).hostname, "port": urlparse(u).port} for u in cluster_nodes]

    redis_manager = RedisManager(
        stop_event=stop_event,
        redis_url=startup_nodes,
        redis_mode="cluster"
    )

    key_new_seen = "test_new_seen_cluster"
    key_is_req = "test_is_req_cluster"
    queue_key = "test_queue_cluster"
    fp = "req_cluster_001"
    req_bytes = b"request_data_cluster"

    await redis_manager.delete(key_new_seen, key_is_req, queue_key)

    res = await redis_manager.do_filter(fp, key_new_seen, key_is_req)
    print("do_filter:", res)

    if res:
        await redis_manager.lpush(queue_key, req_bytes)

    req = await redis_manager.dequeue_request(queue_key, decode_responses=True)
    print("dequeue_request:", req)

    await redis_manager.delete(key_new_seen, key_is_req, queue_key)
    print("CLUSTER test done.\n")


async def main():
    # await test_redis_single()
    await test_redis_sentinel()
    # await test_redis_cluster()


if __name__ == "__main__":
    asyncio.run(main())
