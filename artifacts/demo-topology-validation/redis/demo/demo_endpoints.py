import os


DEMO_HTTP_URL = "http://127.0.0.1:%s" % os.environ.get(
    "SCRAPY_CFFI_DEMO_HTTP_PORT",
    "8002",
)
DEMO_WS_URL = "ws://127.0.0.1:%s" % os.environ.get(
    "SCRAPY_CFFI_DEMO_WS_PORT",
    "8765",
)
