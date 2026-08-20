"""Assemble concrete infrastructure, repositories, and crawler services."""

import asyncio
from typing import TYPE_CHECKING, Optional

from .service import ResourceService, ResourceSlot, RetryPolicy
from .settings import SettingsInfo

if TYPE_CHECKING:
    from logging import Logger


def activate_http_runtime(settings: SettingsInfo) -> None:
    """Activate a configured curl runtime and then register profile metadata."""
    runtime_dir = settings.CURL_CFFI_RUNTIME_DIR
    if runtime_dir is None:
        return
    from .platform.curl_native import activate_curl_native_runtime
    from .profiles import load_profile_manifest

    runtime = activate_curl_native_runtime(runtime_dir)
    load_profile_manifest(runtime.runtime_dir)


def build_resource_service(
    settings: SettingsInfo,
    stop_event: asyncio.Event,
    logger: Optional["Logger"] = None,
) -> ResourceService:
    """Build an unstarted typed resource service from validated settings."""
    resources = ResourceService(logger=logger)
    attempts = settings.INFRA_RETRY_ATTEMPTS
    delay = settings.INFRA_RETRY_DELAY

    if settings.REDIS_INFO.resolved_url:
        from redis.exceptions import ConnectionError as RedisConnectionError
        from redis.exceptions import TimeoutError as RedisTimeoutError

        from .infra.redis import RedisClient
        from .repo.redis import RedisRepository

        slot = ResourceSlot(lambda: RedisClient.from_info(settings.REDIS_INFO))
        policy = RetryPolicy(
            stop_event,
            (RedisConnectionError, RedisTimeoutError),
            max_attempts=attempts,
            retry_delay=delay,
            label="Redis",
            logger=logger,
        )
        resources.register("redis", slot, RedisRepository(slot, policy))

    if settings.MYSQL_INFO.resolved_url:
        from sqlalchemy.exc import DBAPIError, OperationalError

        from .infra.sqlalchemy import MySQLClient
        from .repo.sql import SQLRepository

        slot = ResourceSlot(lambda: MySQLClient.from_info(settings.MYSQL_INFO))
        policy = RetryPolicy(
            stop_event,
            (OperationalError, DBAPIError),
            max_attempts=attempts,
            retry_delay=delay,
            retry_predicate=lambda exc: not any(
                value in str(exc).lower()
                for value in ("unknown database", "access denied", "doesn't exist")
            ),
            label="MySQL",
            logger=logger,
        )
        resources.register("mysql", slot, SQLRepository(slot, policy))

    if settings.POSTGRES_INFO.resolved_url:
        from sqlalchemy.exc import DBAPIError, OperationalError

        from .infra.sqlalchemy import PostgresClient
        from .repo.sql import SQLRepository

        slot = ResourceSlot(lambda: PostgresClient.from_info(settings.POSTGRES_INFO))
        policy = RetryPolicy(
            stop_event,
            (OperationalError, DBAPIError),
            max_attempts=attempts,
            retry_delay=delay,
            retry_predicate=lambda exc: not any(
                value in str(exc).lower()
                for value in (
                    "invalid_catalog_name",
                    "password authentication failed",
                    "does not exist",
                )
            ),
            label="PostgreSQL",
            logger=logger,
        )
        resources.register("postgres", slot, SQLRepository(slot, policy))

    if settings.MONBODB_INFO.resolved_url:
        from pymongo.errors import AutoReconnect, ConnectionFailure, NetworkTimeout

        from .infra.mongodb import MongoClient
        from .repo.mongodb import MongoRepository

        slot = ResourceSlot(lambda: MongoClient.from_info(settings.MONBODB_INFO))
        policy = RetryPolicy(
            stop_event,
            (AutoReconnect, ConnectionFailure, NetworkTimeout),
            max_attempts=attempts,
            retry_delay=delay,
            label="MongoDB",
            logger=logger,
        )
        resources.register("mongodb", slot, MongoRepository(slot, policy))

    if settings.RABBITMQ_INFO.resolved_url:
        from aio_pika.exceptions import AMQPConnectionError, ChannelClosed

        from .infra.rabbitmq import RabbitMQClient
        from .repo.queue import RabbitMQQueueRepository

        slot = ResourceSlot(
            lambda: RabbitMQClient.from_info(
                settings.RABBITMQ_INFO,
                persist=settings.SCHEDULER_PERSIST,
            )
        )
        policy = RetryPolicy(
            stop_event,
            (AMQPConnectionError, ChannelClosed),
            max_attempts=attempts,
            retry_delay=delay,
            label="RabbitMQ",
            logger=logger,
        )
        resources.register("rabbitmq", slot, RabbitMQQueueRepository(slot, policy))

    if settings.KAFKA_INFO.resolved_url:
        from aiokafka.errors import KafkaConnectionError

        from .infra.kafka import KafkaClient
        from .repo.queue import KafkaQueueRepository

        slot = ResourceSlot(lambda: KafkaClient.from_info(settings.KAFKA_INFO))
        policy = RetryPolicy(
            stop_event,
            (KafkaConnectionError,),
            max_attempts=attempts,
            retry_delay=delay,
            label="Kafka",
            logger=logger,
        )
        resources.register("kafka", slot, KafkaQueueRepository(slot, policy))

    return resources


__all__ = ["activate_http_runtime", "build_resource_service"]
