"""Push one URL into the demo Kafka start-topic repository."""

import asyncio
import logging
import os
from typing import List

from scrapy_cffi import build_resource_service
from scrapy_cffi.config import KafkaInfo
from scrapy_cffi.settings import SettingsInfo


def _bootstrap_servers() -> List[str]:
    """Load one or more Kafka bootstrap servers from the environment."""
    raw = os.environ.get(
        "SCRAPY_CFFI_KAFKA_BOOTSTRAP_SERVERS",
        "127.0.0.1:9092",
    )
    servers = [server.strip() for server in raw.split(",") if server.strip()]
    if not servers:
        raise ValueError("SCRAPY_CFFI_KAFKA_BOOTSTRAP_SERVERS cannot be empty")
    return servers


def _kafka_info(servers: List[str]) -> KafkaInfo:
    """Create settings for a single broker or a Kafka cluster."""
    if len(servers) == 1:
        return KafkaInfo(URL=servers[0])
    return KafkaInfo(
        CLUSTER_NODES=servers,
        REPLICATION_FACTOR=len(servers),
    )


async def _main() -> None:
    """Build the standard resource service and publish one start URL."""
    url = os.environ.get("SCRAPY_CFFI_START_URL", "http://127.0.0.1:8002")
    topic = os.environ.get(
        "SCRAPY_CFFI_KAFKA_INGRESS",
        "customRedisSpider_start",
    )
    settings = SettingsInfo(KAFKA_INFO=_kafka_info(_bootstrap_servers()))
    resources = build_resource_service(settings, asyncio.Event())
    await resources.start()
    try:
        if resources.kafka is None:
            raise RuntimeError("Kafka repository is not configured")
        await resources.kafka.push(topic, url.encode("utf-8"))
        logging.getLogger(__name__).info("Published one start request to %s", topic)
    finally:
        await resources.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
