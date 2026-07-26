from scrapy_cffi.utils import ProcessManager


if __name__ == "__main__":
    manager = ProcessManager(
        register_methods=["hello", "Greeter", "counter"],
    )
    manager.start_client()

    print(manager.hello("World"))
    c = manager.counter()
    print(c.inc())
    g = manager.Greeter()
    print(g.greet("Hi"))
