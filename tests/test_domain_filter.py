import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapy_cffi.utils.domain import (
    hostname_from_allowed,
    url_is_from_allowed_domains,
)


def test_hostname_only_match():
    allowed = ["127.0.0.1:8002", "example.com"]
    assert url_is_from_allowed_domains("http://127.0.0.1:8002/student/1", allowed)
    assert url_is_from_allowed_domains("http://127.0.0.1:9999/student/1", allowed)
    assert not url_is_from_allowed_domains("http://evil.com/x", allowed)


def test_scrapy_style_allowed_entry():
    assert hostname_from_allowed("127.0.0.1") == "127.0.0.1"
    assert hostname_from_allowed("127.0.0.1:8002") == "127.0.0.1"
    assert hostname_from_allowed("http://LocalHost:8765") == "localhost"


def test_empty_allowed_allows_all():
    assert url_is_from_allowed_domains("http://any.host/path", [])


if __name__ == "__main__":
    test_hostname_only_match()
    test_scrapy_style_allowed_entry()
    test_empty_allowed_allows_all()
    print("ok")
