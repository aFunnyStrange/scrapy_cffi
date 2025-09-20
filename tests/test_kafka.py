import asyncio
from scrapy_cffi.mq.kafka import KafkaManager  # 替换成实际导入路径

async def main():
    # 1️⃣ 创建 stop_event
    stop_event = asyncio.Event()

    # 2️⃣ 初始化 KafkaManager
    kafka_url = "localhost:9092"  # 或者 ["node1:9092", "node2:9092"] 集群
    kafka_manager = KafkaManager(
        stop_event=stop_event,
        kafka_url=kafka_url,
        consumer_group="test_group"
    )

    # 3️⃣ 连接 Kafka（producer 会自动连接）
    await kafka_manager.connect()
    print("Connected to Kafka")

    # 4️⃣ 定义测试 topic
    topic = "test_topic"

    # 5️⃣ 发送消息
    messages = [b"hello", b"world", b"asyncio"]
    for msg in messages:
        await kafka_manager.produce(topic, msg)
        print(f"Produced: {msg}")

    # 6️⃣ 消费消息
    for _ in range(len(messages)):
        msg = await kafka_manager.consume(topic, timeout_ms=2000)
        print(f"Consumed: {msg}")

    # 7️⃣ 关闭 Kafka 连接
    await kafka_manager.close()
    print("Closed Kafka connection")

if __name__ == "__main__":
    asyncio.run(main())
