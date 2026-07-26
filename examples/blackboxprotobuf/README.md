# Black-box Protobuf examples

The `person/` and `example/` directories compare generated Protobuf messages
with `scrapy_cffi.utils.blackboxprotobuf` decoding and re-encoding.

Install the optional reference package before running them:

```bash
python -m pip install protobuf
python examples/blackboxprotobuf/person/demo.py
python examples/blackboxprotobuf/example/demo.py
```
