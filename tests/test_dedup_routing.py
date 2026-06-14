"""DedupKeyRouter tests without pulling full scrapy_cffi import chain."""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_routing_module():
    scrapy_cffi = types.ModuleType("scrapy_cffi")
    scrapy_cffi.__path__ = [str(ROOT / "scrapy_cffi")]
    sys.modules.setdefault("scrapy_cffi", scrapy_cffi)

    utils = types.ModuleType("scrapy_cffi.utils")
    utils.__path__ = [str(ROOT / "scrapy_cffi" / "utils")]
    sys.modules["scrapy_cffi.utils"] = utils

    algo_spec = importlib.util.spec_from_file_location(
        "scrapy_cffi.utils.algorithm",
        ROOT / "scrapy_cffi" / "utils" / "algorithm.py",
    )
    algo = importlib.util.module_from_spec(algo_spec)
    sys.modules["scrapy_cffi.utils.algorithm"] = algo
    algo_spec.loader.exec_module(algo)

    dupefilter = types.ModuleType("scrapy_cffi.dupefilter")
    dupefilter.__path__ = [str(ROOT / "scrapy_cffi" / "dupefilter")]
    sys.modules["scrapy_cffi.dupefilter"] = dupefilter

    routing_spec = importlib.util.spec_from_file_location(
        "scrapy_cffi.dupefilter.routing",
        ROOT / "scrapy_cffi" / "dupefilter" / "routing.py",
    )
    routing = importlib.util.module_from_spec(routing_spec)
    sys.modules["scrapy_cffi.dupefilter.routing"] = routing
    routing_spec.loader.exec_module(routing)
    return routing


_routing = _load_routing_module()
DedupKeyRouter = _routing.DedupKeyRouter


def test_single_mode_no_node_suffix():
    router = DedupKeyRouter(
        base_new_seen="cffiFilter_new_seen",
        base_sent_seen="cffiFilter_sent_seen",
        redis_mode="single",
        namespace="spider_a",
    )
    keys = router.for_fingerprint("same-fp")
    assert keys.new_seen == "cffiFilter_new_seen:spider_a"
    assert keys.sent_seen == "cffiFilter_sent_seen:spider_a"


def test_cluster_adds_stable_node_suffix():
    nodes = ["127.0.0.1:7000", "127.0.0.1:7001"]
    router = DedupKeyRouter(
        base_new_seen="cffiFilter_new_seen",
        base_sent_seen="cffiFilter_sent_seen",
        redis_mode="cluster",
        cluster_nodes=nodes,
        namespace="w1",
    )
    k1 = router.for_fingerprint("fp-a")
    k2 = router.for_fingerprint("fp-a")
    assert k1 == k2
    assert k1.new_seen.endswith((":7000", ":7001"))
    assert k1.new_seen.startswith("cffiFilter_new_seen:w1:")


if __name__ == "__main__":
    test_single_mode_no_node_suffix()
    test_cluster_adds_stable_node_suffix()
    print("ok")
