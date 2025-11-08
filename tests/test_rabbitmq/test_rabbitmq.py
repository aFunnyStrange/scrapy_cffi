import asyncio
from scrapy_cffi.mq.rabbitmq import RabbitMQManager

async def test_single():
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
    # ✅ Declare the queue (essential step)
    # Note: In the actual framework, the workflow is to first consume from the queue
    # and then push requests back. By the time dequeue_request is called, the queue
    # has already been declared. Therefore, in the framework, you typically do not
    # need to explicitly declare the queue before pushing.
    await manager.declare_queue(queue_name)
    print(f"✅ Queue '{queue_name}' declared on node {manager._mq_url}")

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

async def test_cluster():
    stop_event = asyncio.Event()

    rabbitmq_nodes = [
        "amqp://guest:guest@<PUBLIC_IP>:5672/",
        "amqp://guest:guest@<PUBLIC_IP>:5673/",
        "amqp://guest:guest@<PUBLIC_IP>:5674/"
    ]

    manager = RabbitMQManager(
        stop_event=stop_event,
        rabbitmq_url=rabbitmq_nodes,
        exchange_name="scrapy_cffi",
        persist=True
    )

    # Connect to the RabbitMQ cluster
    await manager.connect()
    print(f"✅ Connected to RabbitMQ node: {manager._mq_url}")

    queue_name = "scrapy_cffi"

    # ✅ Declare the queue (essential step)
    # Note: In the actual framework, the workflow is to first consume from the queue
    # and then push requests back. By the time dequeue_request is called, the queue
    # has already been declared. Therefore, in the framework, you typically do not
    # need to explicitly declare the queue before pushing.
    await manager.declare_queue(queue_name)
    print(f"✅ Queue '{queue_name}' declared on node {manager._mq_url}")

    # Push messages into the queue
    messages = [
        b"http://127.0.0.1:8002",
        b"http://127.0.0.1:8002/school/9999",
        b"http://127.0.0.1:8002/teacher/9999"
    ]
    for msg in messages:
        await manager.rpush(queue_name, msg)
        print(f"🟢 Pushed: {msg}")

    # Wait for a short while to simulate processing
    await asyncio.sleep(20)

    # Check the current queue length
    length = await manager.llen(queue_name)
    print(f"📊 Queue length after push: {length}")

    # Consume messages from the queue
    for _ in range(length):
        msg = await manager.dequeue_request(queue_name, timeout=2)
        print(f"🔵 Popped: {msg}")

    # Check remaining messages in the queue
    length = await manager.llen(queue_name)
    print(f"📊 Queue length after pop: {length}")

    # Delete the queue
    queue = await manager.declare_queue(queue_name)
    await queue.delete()
    print(f"❌ Queue '{queue_name}' deleted")

    # Close the RabbitMQ connection
    await manager.close()
    print("✅ Closed RabbitMQ connection")

if __name__ == "__main__":
    asyncio.run(test_single())

    # asyncio.run(test_cluster())