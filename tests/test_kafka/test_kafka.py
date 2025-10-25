import asyncio
import logging
from scrapy_cffi.mq.kafka import KafkaManager
from scrapy_cffi.utils import KafkaLoggingHandler

async def run_producer(kafka_url: str, done_event: asyncio.Event):
    stop_event = asyncio.Event()
    kafka_manager = KafkaManager(
        stop_event=stop_event,
        kafka_url=kafka_url,
        consumer_group="log_group"
    )
    await kafka_manager.connect()
    print("✅ Producer connected to Kafka")

    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.INFO)

    kafka_handler = KafkaLoggingHandler(kafka_manager, topic="log_topic", stop_event=stop_event)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    kafka_handler.setFormatter(formatter)
    logger.addHandler(kafka_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    for i in range(5):
        logger.info(f"Test log message {i}")
        await asyncio.sleep(0.1)

    stop_event.set()
    await done_event.wait()
    await kafka_manager.close()
    print("✅ Producer closed")

async def run_consumer(kafka_url: str, done_event: asyncio.Event, expected_count: int = 5):
    stop_event = asyncio.Event()
    kafka_manager = KafkaManager(
        stop_event=stop_event,
        kafka_url=kafka_url,
        # consumer_group="log_consumer_group" # Commented out for framework demo testing
    )
    await kafka_manager.connect()
    print("✅ Consumer connected to Kafka")

    consumed_messages = []

    async def consumer_callback(msg: bytes):
        consumed_messages.append(msg)
        print(f"📥 Consumed: {msg.decode()}")

        if len(consumed_messages) >= expected_count:
            done_event.set()

    await kafka_manager.register_consumer("scrapy_cffi", consumer_callback) # For framework demo testing, comment out next line
    # await kafka_manager.register_consumer("log_topic", consumer_callback, auto_offset_reset="latest")  # For this test file

    await done_event.wait()
    print(f"✅ All consumed messages: {[m.decode() for m in consumed_messages]}")
    await kafka_manager.close()
    print("✅ Consumer closed")


async def main():
    kafka_url = "localhost:9092"
    done_event = asyncio.Event()

    await asyncio.gather(
        # run_producer(kafka_url, done_event), # Uncomment to run producer
        run_consumer(kafka_url, done_event),
    )

if __name__ == "__main__":
    asyncio.run(main())


"""
1.After debug
docker exec -it kafka kafka-topics.sh --bootstrap-server localhost:9092 --list
docker exec -it kafka kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic <topic>

2.Optional
docker exec -it kafka kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list
docker exec -it kafka kafka-consumer-groups.sh --bootstrap-server localhost:9092 --delete --group <group>
"""