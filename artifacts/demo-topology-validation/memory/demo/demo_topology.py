import os

from scrapy_cffi.models.databases import RedisInfo
from scrapy_cffi.models.mq import KafkaInfo, RabbitMQInfo


DEMO_MODE = "memory"


def apply_demo_topology(settings) -> None:
    topology = os.environ.get("SCRAPY_CFFI_DEMO_TOPOLOGY", "single").lower()
    log_file = os.environ.get("SCRAPY_CFFI_DEMO_LOG")
    if log_file:
        settings.LOG_INFO.LOG_FILE = log_file

    if DEMO_MODE == "memory" or topology == "single":
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
        raise ValueError(
            "SCRAPY_CFFI_DEMO_TOPOLOGY must be single, sentinel or cluster"
        )

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
    if DEMO_MODE == "rabbitmq":
        settings.RABBITMQ_INFO = RabbitMQInfo(
            CLUSTER_NODES=[
                "amqp://guest:guest@127.0.0.1:5672/",
                "amqp://guest:guest@127.0.0.1:5673/",
                "amqp://guest:guest@127.0.0.1:5674/",
            ]
        )
    elif DEMO_MODE == "kafka":
        settings.KAFKA_INFO = KafkaInfo(
            CLUSTER_NODES=[
                "127.0.0.1:9094",
                "127.0.0.1:9095",
                "127.0.0.1:9096",
            ],
            REPLICATION_FACTOR=3,
        )
