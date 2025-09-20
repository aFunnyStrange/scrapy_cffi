try:
    import aio_pika
except ImportError as e:
    raise ImportError(
        "Missing aio_pika dependencies. "
        "Please install: pip install aio_pika"
    ) from e

