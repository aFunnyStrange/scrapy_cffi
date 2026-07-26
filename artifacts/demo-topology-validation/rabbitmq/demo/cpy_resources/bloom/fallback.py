import math
from typing import Union

def fnv1a_hash(data: Union[str, bytes], seed: int = 0) -> int:
    if isinstance(data, str):
        data = data.encode("utf-8")
    hash_ = 2166136261 ^ seed
    for b in data:
        hash_ ^= b
        hash_ = (hash_ * 16777619) & 0xFFFFFFFF
    return hash_

def set_bit(array: bytearray, index: int):
    array[index // 8] |= 1 << (index % 8)

def get_bit(array: bytearray, index: int) -> bool:
    return (array[index // 8] >> (index % 8)) & 1

class BloomFilterPy:
    def __init__(self, size: int, expected: int, hash_count: int = 0):
        self.size = size
        self.bytes = (size + 7) // 8
        self.bit_array = bytearray(self.bytes)
        self.inserted = 0
        if hash_count == 0:
            self.hash_count = max(1, round(size / expected * math.log(2)))
        else:
            self.hash_count = hash_count

    def add(self, data: Union[str, bytes]):
        for i in range(self.hash_count):
            h = fnv1a_hash(data, i)
            index = h % self.size
            set_bit(self.bit_array, index)
        self.inserted += 1

    def exists(self, data: Union[str, bytes]) -> bool:
        for i in range(self.hash_count):
            h = fnv1a_hash(data, i)
            index = h % self.size
            if not get_bit(self.bit_array, index):
                return False
        return True
    
    def free(self):
        """
        C extension previously used for ~30% faster inserts,
        but due to strong OS and Python version dependencies,
        related compiled files need to be built manually.
        This interface is the fallback version for the C extension,
        keeping full API compatibility.
        """
        pass

    def clear(self):
        self.bit_array = bytearray(self.bytes)
        self.inserted = 0

    def estimated_false_positive_rate(self) -> float:
        if self.inserted == 0:
            return 0.0
        m = self.size
        k = self.hash_count
        n = self.inserted
        return (1.0 - math.exp(-k * n / m)) ** k

    def get_hash_count(self) -> int:
        return self.hash_count

    def get_indices(self, data: Union[str, bytes]) -> list[int]:
        indices = []
        for i in range(self.hash_count):
            h = fnv1a_hash(data, i)
            indices.append(h % self.size)
        return indices
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.free()

try:
    from wrapper import BloomFilter as _C_BloomFilter
    BloomFilter = _C_BloomFilter
except (ImportError, OSError):
    # fallback
    BloomFilter = BloomFilterPy

__all__ = [
    "BloomFilter"
]

if __name__ == "__main__":
    bf = BloomFilter(size=1000, expected=100, hash_count=0)
    print(bf.get_hash_count())
    bf.add("asgshyjhyt")
    bf.add("asgyiylo98")
    bf.add("asgyiylo96687")
    print(bf.get_indices("daafasg"))