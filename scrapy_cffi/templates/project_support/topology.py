"""Apply optional single-machine or clustered infrastructure endpoints."""

import os

from scrapy_cffi.config.database import RedisInfo
from scrapy_cffi.config.queue import KafkaInfo, RabbitMQInfo
from scrapy_cffi.scheduler import KafkaScheduler, RabbitMqScheduler


def apply_project_topology(settings) -> None:
    """Apply project topology overrides selected through the environment."""
    topology = os.environ.get("SCRAPY_CFFI_TOPOLOGY", "single").lower()
    log_file = os.environ.get("SCRAPY_CFFI_LOG")
    if log_file:
        settings.LOG_INFO.LOG_FILE = log_file

    if topology == "single":
        return

    if topology == "sentinel":
        settings.REDIS_INFO = RedisInfo(
            SENTINELS=[
                ("127.0.0.1", 26379),
                ("127.0.0.1", 26380),
                ("127.0.0.1", 26381),
            ],
            MASTER_NAME="mymaster",
            SENTINEL_OVERRIDE_MASTER=("127.0.0.1", 6379),
        )
        return

    if topology != "cluster":
        raise ValueError("SCRAPY_CFFI_TOPOLOGY must be single, sentinel or cluster")

    settings.REDIS_INFO = RedisInfo(
        CLUSTER_NODES=[
            {"host": "127.0.0.1", "port": port}
            for port in range(7000, 7006)
        ],
        CLUSTER_ADDRESS_REMAP={
            "host.docker.internal": "127.0.0.1",
            "redis-node1": "127.0.0.1",
            "redis-node2": "127.0.0.1",
            "redis-node3": "127.0.0.1",
            "redis-node4": "127.0.0.1",
            "redis-node5": "127.0.0.1",
            "redis-node6": "127.0.0.1",
        },
    )
    if settings.SCHEDULER is RabbitMqScheduler:
        settings.RABBITMQ_INFO = RabbitMQInfo(
            CLUSTER_NODES=[
                "amqp://guest:guest@127.0.0.1:5672/",
                "amqp://guest:guest@127.0.0.1:5673/",
                "amqp://guest:guest@127.0.0.1:5674/",
            ]
        )
    elif settings.SCHEDULER is KafkaScheduler:
        settings.KAFKA_INFO = KafkaInfo(
            CLUSTER_NODES=[
                "127.0.0.1:9094",
                "127.0.0.1:9095",
                "127.0.0.1:9096",
            ],
            REPLICATION_FACTOR=3,
        )
