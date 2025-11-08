# pip install protobuf==6.33.0
import example_pb2
import base64
from scrapy_cffi.utils import blackboxprotobuf

# ====== protobuf ======
person = example_pb2.Person()
person.id = 123
person.name = "Alice"
person.active = True
person.nickname = "Ally"
person.emails.extend(["alice@example.com", "alice@work.com"])
person.attributes["role"] = "admin"
person.attributes["team"] = "dev"

address = example_pb2.Address()
address.street = "123 Main St"
address.city = "Metropolis"
address.country = "Neverland"
person.address.CopyFrom(address)

# to binary
binary_data = person.SerializeToString()
print("protobuf encode（hex）:", binary_data.hex())
print("protobuf encode（base64）:", base64.b64encode(binary_data).decode('utf-8'))

# decode
decoded = example_pb2.Person()
decoded.ParseFromString(binary_data)
print("protobuf decode:", decoded)

# ====== blackboxprotobuf ======
decoded_data, decoded_typedef = blackboxprotobuf.decode_message(binary_data)
print("blackboxprotobuf decode data:", decoded_data)
print("blackboxprotobuf decode typedef:", decoded_typedef)


blackboxprotobuf_binary = blackboxprotobuf.encode_message(decoded_data, decoded_typedef)

decoded.ParseFromString(blackboxprotobuf_binary)
print("protobuf decode:", decoded)