from scrapy_cffi.utils import blackboxprotobuf


def test_blackboxprotobuf_round_trip():
    payload = {"1": "aaa", "2": b"\xff\x00"}
    typedef = {
        "1": {"type": "string"},
        "2": {"type": "bytes"},
    }

    encoded = blackboxprotobuf.encode_message(payload, typedef)
    decoded, decoded_typedef = blackboxprotobuf.decode_message(encoded)

    assert decoded == payload
    assert decoded_typedef["1"]["type"] == "string"
    assert decoded_typedef["2"]["type"] == "bytes"
