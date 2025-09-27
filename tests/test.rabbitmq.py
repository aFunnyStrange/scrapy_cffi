import asyncio
from scrapy_cffi.mq.rabbitmq import RabbitMQManager

async def main():
    # 1️⃣ Create a stop event
    stop_event = asyncio.Event()

    # 2️⃣ Initialize RabbitMQManager
    rabbitmq_url = "amqp://guest:guest@localhost/"
    manager = RabbitMQManager(
        stop_event=stop_event,
        rabbitmq_url=rabbitmq_url,
        exchange_name="scrapy_cffi",
        persist=True
    )

    # 3️⃣ Connect to RabbitMQ
    await manager.connect()
    print("Connected to RabbitMQ")

    # 4️⃣ Define the test queue
    queue_name = "scrapy_cffi"

    # 5️⃣ Push messages to the queue
    messages = [
        b"http://127.0.0.1:8002", 
        b"http://127.0.0.1:8002/school/9999", 
        b"http://127.0.0.1:8002/teacher/9999"
    ]
    for msg in messages:
        await manager.rpush(queue_name, msg)
        print(f"Pushed: {msg}")

    # 6️⃣ Pop messages from the queue
    # for _ in range(len(messages)):
    #     msg = await manager.dequeue_request(queue_name, timeout=2)
    #     print(f"Popped: {msg}")

    # 7️⃣ Check the queue length
    length = await manager.llen(queue_name)
    print(f"Queue length after consuming: {length}")

    # 8️⃣ Close the connection
    await manager.close()
    print("Closed RabbitMQ connection")

if __name__ == "__main__":
    asyncio.run(main())