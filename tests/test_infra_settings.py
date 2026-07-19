import pytest

from scrapy_cffi.models.databases import RedisInfo, RedisMode
from scrapy_cffi.models.mq import KafkaInfo, MQMode, RabbitMQInfo


def test_redis_topology_is_inferred_from_real_machine_nodes():
    sentinel = RedisInfo(
        SENTINELS=[("sentinel-01.internal", 26379)],
        MASTER_NAME="mymaster",
        USERNAME="crawler",
        PASSWORD="secret",
    )
    cluster = RedisInfo(
        CLUSTER_NODES=["redis-01.internal:6379", "redis-02.internal:6379"],
        CLUSTER_ADDRESS_REMAP={"redis-private-01": "redis-01.internal"},
    )

    assert sentinel.MODE == RedisMode.SENTINEL
    assert cluster.MODE == RedisMode.CLUSTER
    assert cluster.resolved_url == ["redis-01.internal:6379", "redis-02.internal:6379"]


def test_redis_rejects_ambiguous_topology():
    with pytest.raises(ValueError, match="either SENTINELS or CLUSTER_NODES"):
        RedisInfo(
            SENTINELS=[("sentinel-01.internal", 26379)],
            MASTER_NAME="mymaster",
            CLUSTER_NODES=["redis-01.internal:6379"],
        )


def test_mq_cluster_mode_and_kafka_replication_are_inferred():
    rabbit = RabbitMQInfo(
        CLUSTER_NODES=[
            "amqps://crawler:secret@rabbit-01.internal:5671/scrapy",
            "amqps://crawler:secret@rabbit-02.internal:5671/scrapy",
        ]
    )
    kafka = KafkaInfo(
        CLUSTER_NODES=[
            "kafka-01.internal:9093",
            "kafka-02.internal:9093",
            "kafka-03.internal:9093",
        ],
        SECURITY_PROTOCOL="SASL_SSL",
        SASL_MECHANISM="SCRAM-SHA-512",
        SASL_USERNAME="crawler",
        SASL_PASSWORD="secret",
    )

    assert rabbit.MODE == MQMode.CLUSTER
    assert kafka.MODE == MQMode.CLUSTER
    assert kafka.REPLICATION_FACTOR == 3


def test_kafka_host_port_uses_native_bootstrap_format():
    kafka = KafkaInfo(HOST="kafka.internal", PORT=9093)

    assert kafka.URL == "kafka.internal:9093"
