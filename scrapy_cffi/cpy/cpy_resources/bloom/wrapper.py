import os, sys
from ctypes import CDLL, c_void_p, c_char_p, c_bool, c_size_t, POINTER
from pathlib import Path
from typing import Union

dir = Path(__file__).parent
if os.name.lower() == "nt":
    # Windows
    lib = CDLL(str(dir / "build" / "libbloom.dll"))
elif sys.platform == "darwin":
    # macOS
    lib = CDLL(str(dir / "build" / "libbloom.dylib"))
else:
    # Linux / 其他 Unix
    lib = CDLL(str(dir / "build" / "libbloom.so"))

lib.bloom_init.restype = c_void_p
lib.bloom_init.argtypes = [c_size_t, c_size_t, c_size_t]

lib.bloom_add.argtypes = [c_void_p, c_char_p, c_size_t]
lib.bloom_add.restype = None

lib.bloom_exists.argtypes = [c_void_p, c_char_p, c_size_t]
lib.bloom_exists.restype = c_bool

lib.bloom_free.argtypes = [c_void_p]

lib.bloom_clear.argtypes = [c_void_p]

lib.bloom_estimated_false_positive_rate.argtypes = [c_void_p]
lib.bloom_estimated_false_positive_rate.restype = float

lib.bloom_get_hash_count.restype = c_size_t
lib.bloom_get_hash_count.argtypes = [c_void_p]

lib.bloom_get_indices.argtypes = [c_void_p, c_char_p, c_size_t, POINTER(c_size_t)]
lib.bloom_get_indices.restype = c_size_t

# Python 封装函数
def bloom_init(size: int, expected: int, k: int = 0) -> c_void_p:
    return lib.bloom_init(size, expected, k)

def bloom_add(filter_ptr: c_void_p, data: Union[str, bytes]):
    if isinstance(data, str):
        data = data.encode()
    lib.bloom_add(filter_ptr, data, len(data))

def bloom_exists(filter_ptr: c_void_p, data: Union[str, bytes]) -> bool:
    if isinstance(data, str):
        data = data.encode()
    return lib.bloom_exists(filter_ptr, data, len(data))

def bloom_free(filter_ptr: c_void_p):
    lib.bloom_free(filter_ptr)

def bloom_clear(filter_ptr: c_void_p):
    lib.bloom_clear(filter_ptr)

def bloom_estimated_false_positive_rate(filter_ptr: c_void_p) -> float:
    return lib.bloom_estimated_false_positive_rate(filter_ptr)

def bloom_get_hash_count(filter_ptr: c_void_p) -> int:
    return lib.bloom_get_hash_count(filter_ptr)

def bloom_get_indices(filter_ptr: c_void_p, data: Union[str, bytes]) -> list[int]:
    if isinstance(data, str):
        data = data.encode()
    hash_count = bloom_get_hash_count(filter_ptr)
    indices_array = (c_size_t * hash_count)()
    count = lib.bloom_get_indices(filter_ptr, data, len(data), indices_array)
    return [indices_array[i] for i in range(count)]

class BloomFilter:
    def __init__(self, size: int, expected: int, hash_count: int = 0):
        self._ptr = bloom_init(size, expected, hash_count)

    def add(self, data: Union[str, bytes]):
        bloom_add(self._ptr, data)

    def exists(self, data: Union[str, bytes]) -> bool:
        return bloom_exists(self._ptr, data)
    
    def free(self):
        bloom_free(self._ptr)

    def clear(self):
        bloom_clear(self._ptr)

    def estimated_false_positive_rate(self) -> float:
        return bloom_estimated_false_positive_rate(self._ptr)

    def get_hash_count(self) -> int:
        return bloom_get_hash_count(self._ptr)

    def get_indices(self, data: Union[str, bytes]) -> list[int]:
        return bloom_get_indices(self._ptr, data)
    
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.free()

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