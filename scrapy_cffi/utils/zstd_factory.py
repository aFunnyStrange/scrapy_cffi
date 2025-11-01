try:
    import zstandard as zstd
except ImportError as e:
    raise ImportError(
        "Missing zstandard dependencies. "
        "Please install: pip install zstandard"
    ) from e

from typing import Optional

class ZstdFactory:
    @staticmethod
    def encode(data: bytes, level: int = 3, dict_data: Optional[bytes] = None) -> bytes:
        cctx = zstd.ZstdCompressor(level=level, dict_data=dict_data)
        return cctx.compress(data)

    @staticmethod
    def decode(data: bytes, dict_data: Optional[bytes] = None) -> bytes:
        dctx = zstd.ZstdDecompressor(dict_data=dict_data)
        try:
            return dctx.decompress(data)
        except Exception as e:
            raise ValueError("Unable to zstd-decompress.") from e

__all__ = [
    "ZstdFactory"
]
