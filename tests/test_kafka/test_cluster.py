import asyncio
import logging
from scrapy_cffi.mq.kafka import KafkaManager

TOPIC = "cluster_test_topic"

async def run_producer(kafka_urls: list, stop_event: asyncio.Event, done_event: asyncio.Event):
    kafka_manager = KafkaManager(
        stop_event=stop_event,
        kafka_url=kafka_urls,
        consumer_group="cluster_producer"
    )

    await kafka_manager.connect()
    print("✅ Producer connected to Kafka cluster")

    await kafka_manager.ensure_topic(TOPIC, num_partitions=3, replication_factor=3)

    logger = logging.getLogger("cluster_producer")
    logger.setLevel(logging.INFO)

    class KafkaLoggingHandler(logging.Handler):
        def emit(self, record):
            msg = self.format(record)
            asyncio.create_task(kafka_manager.produce_async(TOPIC, msg.encode()))

    handler = KafkaLoggingHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)

    for i in range(10):
        logger.info(f"Message {i} from producer")
        await asyncio.sleep(0.5)

    done_event.set()
    await asyncio.sleep(2)
    await kafka_manager.close()
    print("✅ Producer closed")


async def run_consumer(kafka_urls: list, stop_event: asyncio.Event, done_event: asyncio.Event):
    kafka_manager = KafkaManager(
        stop_event=stop_event,
        kafka_url=kafka_urls,
        consumer_group="cluster_consumer"
    )

    await kafka_manager.connect()
    print("✅ Consumer connected to Kafka cluster")

    received = []

    async def on_message(msg: bytes):
        text = msg.decode()
        received.append(text)
        print(f"📥 Consumed: {text}")
        if len(received) >= 10:
            done_event.set()

    await kafka_manager.register_consumer(TOPIC, on_message, auto_offset_reset="earliest")

    await done_event.wait()
    print(f"✅ Received {len(received)} messages")
    await kafka_manager.close()
    print("✅ Consumer closed")


async def main():
    kafka_urls = ["localhost:9094", "localhost:9095", "localhost:9096"]

    producer_done = asyncio.Event()
    consumer_done = asyncio.Event()

    stop_event = asyncio.Event()

    await asyncio.gather(
        run_consumer(kafka_urls, stop_event, consumer_done),
        run_producer(kafka_urls, stop_event, producer_done),
    )

    stop_event.set()
    print("🎉 Cluster test finished successfully.")


if __name__ == "__main__":
    asyncio.run(main())
