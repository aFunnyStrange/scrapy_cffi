from scrapy_cffi.utils import ProcessManager

# 1. Function
def hello(name: str):
    return f"Hello, {name}!"


# 2. Class
class Greeter:
    def greet(self, msg: str):
        return f"Greeting: {msg}"


# 3. Object instance
class Counter:
    def __init__(self):
        self.value = 0

    def inc(self):
        self.value += 1
        return self.value

    def get(self):
        return self.value


counter = Counter()

if __name__ == "__main__":
    manager = ProcessManager(
        register_methods={
            "hello": hello,
            "Greeter": Greeter,
            "counter": counter,
        }
    )
    manager.start_server(run_mode=0)  # blocking mode
