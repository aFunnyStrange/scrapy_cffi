# Test whether the logic is correct after refactoring
from scrapy_cffi.utils import blackboxprotobuf

if __name__ == "__main__":
    data = {"1": "aaa", "2": b'bbbbbbb'}
    typedef = {
        "1": {"type": "string"},
        "2": {"type": "bytes"}
    }
    data = blackboxprotobuf.encode_message(data, typedef)
    print(data)

    decode_data, decode_typedef = blackboxprotobuf.decode_message(data)
    print(decode_data)
    print(decode_typedef)