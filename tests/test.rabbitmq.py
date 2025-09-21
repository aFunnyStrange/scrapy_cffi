import asyncio
from scrapy_cffi.mq.rabbitmq import RabbitMQManager

async def main():
    # 1️⃣ 创建 stop_event
    stop_event = asyncio.Event()

    # 2️⃣ 初始化 RabbitMQManager
    rabbitmq_url = "amqp://guest:guest@localhost/"
    manager = RabbitMQManager(
        stop_event=stop_event,
        rabbitmq_url=rabbitmq_url,
        exchange_name="scrapy_cffi",
        persist=True
    )

    # 3️⃣ 连接 RabbitMQ
    await manager.connect()
    print("Connected to RabbitMQ")

    # 4️⃣ 定义测试队列
    queue_name = "scrapy_cffi"

    # 5️⃣ 往队列推送消息
    messages = [b"http://127.0.0.1:8002", b"http://127.0.0.1:8002/school/9999", b"http://127.0.0.1:8002/teacher/9999"]
    for msg in messages:
        await manager.rpush(queue_name, msg)
        print(f"Pushed: {msg}")

    # 6️⃣ 从队列取出消息
    # for _ in range(len(messages)):
    #     msg = await manager.dequeue_request(queue_name, timeout=2)
    #     print(f"Popped: {msg}")

    # 7️⃣ 查询队列长度
    length = await manager.llen(queue_name)
    print(f"Queue length after consuming: {length}")

    # 8️⃣ 关闭连接
    await manager.close()
    print("Closed RabbitMQ connection")

if __name__ == "__main__":
    asyncio.run(main())