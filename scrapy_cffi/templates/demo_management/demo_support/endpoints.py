import os


DEMO_HTTP_URL = "http://127.0.0.1:%s" % os.environ.get(
    "SCRAPY_CFFI_DEMO_HTTP_PORT",
    "8002",
)
DEMO_WS_URL = "ws://127.0.0.1:%s" % os.environ.get(
    "SCRAPY_CFFI_DEMO_WS_PORT",
    "8765",
)
DEMO_PROCESS_URL = "%s/process-task?delay=0.05&value=21" % DEMO_HTTP_URL
DEMO_QUIC_URL = "https://127.0.0.1:%s/" % os.environ.get(
    "SCRAPY_CFFI_DEMO_QUIC_PORT",
    "18443",
)
