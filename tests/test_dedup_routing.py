"""DedupKeyRouter tests."""

from scrapy_cffi.dupefilter.routing import DedupKeyRouter


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
    assert any(node in k1.new_seen for node in nodes)
    assert k1.new_seen.startswith("cffiFilter_new_seen:w1:")
    assert "{" in k1.new_seen and k1.new_seen.endswith("}")


if __name__ == "__main__":
    test_single_mode_no_node_suffix()
    test_cluster_adds_stable_node_suffix()
    print("ok")
