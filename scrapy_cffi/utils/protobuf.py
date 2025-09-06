import blackboxprotobuf, gzip
from typing import Union, Dict, List, Tuple

class ProtobufFactory(object):
    @staticmethod
    def protobuf_encode(data: Dict, typedef: Dict) -> bytes:
        return blackboxprotobuf.encode_message(data, typedef)

    @staticmethod
    def protobuf_decode(data: bytes) -> Tuple[Dict, Dict]:
        data, typedef = blackboxprotobuf.decode_message(data)
        return data, typedef

    @staticmethod
    def encode_message_length(length: int) -> bytes:
        if not (0 <= length <= 0xFFFFFFFF):
            raise ValueError("Message length must be between 0 and 2^32-1")
        return length.to_bytes(4, byteorder="big")

    @staticmethod
    def decode_message_length(data: bytes) -> int:
        if len(data) != 4:
            raise ValueError("Expected 4 bytes for message length")
        return int.from_bytes(data, byteorder="big")

    @staticmethod
    def grpc_encode(data: Dict, typedef: Dict, is_gzip: bool=False) -> bytes:
        encode_data = ProtobufFactory.protobuf_encode(data, typedef)
        if is_gzip:
            encode_data = gzip.compress(encode_data)
            return bytes([1]) + ProtobufFactory.encode_message_length(len(encode_data)) + encode_data
        return bytes([0]) + ProtobufFactory.encode_message_length(len(encode_data)) + encode_data
    
    @staticmethod
    def grpc_stream_encode(data: List[Tuple[Dict, Dict]], is_gzip=False) -> bytes:
        stream_bytes = b""
        for data, typedef in data:
            encoded_msg = ProtobufFactory.grpc_encode(data, typedef, is_gzip)
            stream_bytes += encoded_msg
        return stream_bytes
        
    @staticmethod
    def grpc_decode(data: bytes) -> Union[Tuple[Dict, Dict], List[Tuple[Dict, Dict]]]:
        results = []
        offset = 0
        total_len = len(data)

        while offset < total_len:
            if total_len - offset < 5:
                raise ValueError("Incomplete grpc message header")

            compress_flag = data[offset]
            offset += 1

            msg_length_bytes = data[offset:offset+4]
            if len(msg_length_bytes) < 4:
                raise ValueError("Incomplete grpc message length")
            msg_length = ProtobufFactory.decode_message_length(msg_length_bytes)
            offset += 4

            if total_len - offset < msg_length:
                raise ValueError("Incomplete grpc message body")
            message_data = data[offset:offset+msg_length]
            offset += msg_length
            if compress_flag == 1:
                decompressed = gzip.decompress(message_data)
                decoded_data, typedef = ProtobufFactory.protobuf_decode(decompressed)
            else:
                decoded_data, typedef = ProtobufFactory.protobuf_decode(message_data)
            results.append((decoded_data, typedef))
        return results[0] if len(results) == 1 else results
    
__all__ = [
    "ProtobufFactory"
]