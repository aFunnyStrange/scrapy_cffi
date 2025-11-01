try:
    import lz4.frame
    import lz4.block
except ImportError as e:
    raise ImportError(
        "Missing lz4 dependencies. "
        "Please install: pip install lz4"
    ) from e

class Lz4Factory(object):
    @staticmethod
    def frame_encode(data: bytes, compression_level: int = 0) -> bytes:
        return lz4.frame.compress(data, compression_level=compression_level)

    @staticmethod
    def frame_decode(data: bytes) -> bytes:
        return lz4.frame.decompress(data)

    @staticmethod
    def block_encode(data: bytes, compression: bool = True) -> bytes:
        return lz4.block.compress(data) if compression else data

    @staticmethod
    def block_decode(data: bytes, uncompressed_size: int = None) -> bytes:
        if uncompressed_size:
            return lz4.block.decompress(data, uncompressed_size=uncompressed_size)

        if not uncompressed_size:
            last_exc = None
            uncompressed_size_list = [len(data)*3, len(data)*5, int(1024e3)]
            for uncompressed_size in uncompressed_size_list:
                try:
                    return lz4.block.decompress(data, uncompressed_size=uncompressed_size)
                except Exception as e:
                    last_exc = e
            raise ValueError("Unable to lz4-decompress.") from last_exc
    
__all__ = [
    "Lz4Factory"
]