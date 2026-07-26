# pip install protobuf==6.33.0
import person_pb2
import base64
from scrapy_cffi.utils import blackboxprotobuf

# ====== protobuf ======
person = person_pb2.Person()
person.id = 123
person.name = "Alice"
person.active = True

# to binary
binary_data = person.SerializeToString()
print("protobuf encoded (hex):", binary_data.hex())
print("protobuf encoded (base64):", base64.b64encode(binary_data).decode("utf-8"))

# decode
decoded = person_pb2.Person()
decoded.ParseFromString(binary_data)
print("protobuf decode:")
print("  id =", decoded.id)
print("  name =", decoded.name)
print("  active =", decoded.active)


# ====== blackboxprotobuf ======
decoded_data, decoded_typedef = blackboxprotobuf.decode_message(binary_data)
print("blackboxprotobuf decode data:", decoded_data)
print("blackboxprotobuf decode typedef:", decoded_typedef)


blackboxprotobuf_binary = blackboxprotobuf.encode_message(decoded_data, decoded_typedef)

decoded.ParseFromString(blackboxprotobuf_binary)
print("protobuf decode:")
print("  id =", decoded.id)
print("  name =", decoded.name)
print("  active =", decoded.active)
