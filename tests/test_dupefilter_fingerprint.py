"""Dupefilter fingerprint: URL query param order should not affect fingerprint."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapy_cffi.core.downloader.internet import HttpRequest
from scrapy_cffi.dupefilter.fingerprint import canonical_request_url
from scrapy_cffi.dupefilter.base import BaseFingerprint
from scrapy_cffi.settings import SettingsInfo


def test_canonical_url_sorts_query_params():
    assert canonical_request_url("http://x/a?b=2&a=1") == "http://x/a?a=1&b=2"
    assert canonical_request_url("http://x/a?a=1&b=2") == "http://x/a?a=1&b=2"
    assert canonical_request_url("http://x/a") == "http://x/a"


def test_fingerprint_ignores_param_order():
    fp = BaseFingerprint(settings=SettingsInfo())
    r1 = HttpRequest(url="http://example.com/path", params={"b": "2", "a": "1"})
    r2 = HttpRequest(url="http://example.com/path", params={"a": "1", "b": "2"})
    assert fp.get_fingerprint(r1) == fp.get_fingerprint(r2)


if __name__ == "__main__":
    test_canonical_url_sorts_query_params()
    test_fingerprint_ignores_param_order()
    print("ok")
