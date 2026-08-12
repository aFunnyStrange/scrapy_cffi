"""Provide one stable Bloom-filter API over Rust and pure-Python backends."""

import logging
import math
from importlib import import_module
from typing import Any, Callable, List, Protocol, Union, cast

from ppxxh import xxh3_64


BloomValue = Union[str, bytes, bytearray, memoryview]
Importer = Callable[[str], Any]
logger = logging.getLogger(__name__)


class BloomFilterProtocol(Protocol):
    """Describe Bloom operations consumed by local and Redis deduplication."""

    backend_name: str
    algorithm_name: str

    def add(self, data: BloomValue) -> None:
        """Record one value in the filter."""
        ...

    def exists(self, data: BloomValue) -> bool:
        """Return whether one value may already be present."""
        ...

    def free(self) -> None:
        """Release backend-owned state when applicable."""
        ...

    def clear(self) -> None:
        """Reset all bitmap bits and insertion statistics."""
        ...

    def estimated_false_positive_rate(self) -> float:
        """Estimate the current false-positive rate."""
        ...

    def get_hash_count(self) -> int:
        """Return the number of bitmap probes per value."""
        ...

    def get_indices(self, data: BloomValue) -> List[int]:
        """Return deterministic indices used by Redis bitmap operations."""
        ...


def _as_bytes(data: BloomValue) -> bytes:
    """Normalize the stable public value types to bytes."""
    if isinstance(data, str):
        return data.encode("utf-8")
    if isinstance(data, bytes):
        return data
    if isinstance(data, (bytearray, memoryview)):
        return bytes(data)
    raise TypeError("Bloom filter values must be str or bytes-like")


def _hash_count(size: int, expected: int, configured: int) -> int:
    """Resolve the optimal number of hashes when no override is configured."""
    if size <= 0:
        raise ValueError("Bloom size must be greater than zero")
    if expected <= 0:
        raise ValueError("Bloom expected items must be greater than zero")
    if configured < 0:
        raise ValueError("Bloom hash count cannot be negative")
    if configured:
        return configured
    return max(1, round(size / expected * math.log(2)))


def _indices(data: BloomValue, size: int, hash_count: int) -> List[int]:
    """Derive Kirsch-Mitzenmacher indices from two stable XXH3 hashes."""
    raw = _as_bytes(data)
    hash_one = xxh3_64(raw, seed=0).intdigest() % size
    hash_two = xxh3_64(raw, seed=32).intdigest() % size
    return [
        hash_one if index == 0 else (hash_one + index * hash_two) % size
        for index in range(hash_count)
    ]


class PythonBloomFilter:
    """Implement the optimized XXH3 Bloom algorithm in portable Python."""

    backend_name = "python"
    algorithm_name = "xxh3-km-v1"

    def __init__(self, size: int, expected: int, hash_count: int = 0) -> None:
        """Allocate one byte-aligned bitmap using validated dimensions."""
        self.size = ((size + 7) // 8) * 8
        self.expected = expected
        self.hash_count = _hash_count(self.size, expected, hash_count)
        self.bit_array = bytearray(self.size // 8)
        self.inserted = 0

    def add(self, data: BloomValue) -> None:
        """Set every derived bitmap index for one value."""
        for index in self.get_indices(data):
            self.bit_array[index // 8] |= 1 << (index % 8)
        self.inserted += 1

    def exists(self, data: BloomValue) -> bool:
        """Return false when any derived bitmap bit is absent."""
        return all(
            (self.bit_array[index // 8] >> (index % 8)) & 1
            for index in self.get_indices(data)
        )

    def free(self) -> None:
        """Release the portable bitmap eagerly."""
        self.bit_array = bytearray()
        self.inserted = 0

    def clear(self) -> None:
        """Reset all bits while retaining the configured size."""
        self.bit_array = bytearray(self.size // 8)
        self.inserted = 0

    def estimated_false_positive_rate(self) -> float:
        """Estimate the current rate from add operations."""
        if self.inserted == 0:
            return 0.0
        return (
            1.0
            - math.exp(-self.hash_count * self.inserted / self.size)
        ) ** self.hash_count

    def get_hash_count(self) -> int:
        """Return the number of probes per value."""
        return self.hash_count

    def get_indices(self, data: BloomValue) -> List[int]:
        """Return deterministic XXH3 double-hash indices."""
        return _indices(data, self.size, self.hash_count)


class RustBloomFilter:
    """Adapt fastbloom-rs while retaining the framework-owned API."""

    backend_name = "rust"
    algorithm_name = "xxh3-km-v1"

    def __init__(
        self,
        native_type: Any,
        size: int,
        expected: int,
        hash_count: int = 0,
    ) -> None:
        """Build an empty native bitmap with framework-controlled dimensions."""
        self.size = ((size + 7) // 8) * 8
        self.expected = expected
        self.hash_count = _hash_count(self.size, expected, hash_count)
        self._native_type = native_type
        self._native = native_type.from_bytes(
            bytes(self.size // 8),
            self.hash_count,
        )
        self.inserted = 0

    def add(self, data: BloomValue) -> None:
        """Add one normalized value through the native backend."""
        self._native.add_bytes(_as_bytes(data))
        self.inserted += 1

    def exists(self, data: BloomValue) -> bool:
        """Check one normalized value through the native backend."""
        return bool(self._native.contains_bytes(_as_bytes(data)))

    def free(self) -> None:
        """Release native state by dropping its last adapter reference."""
        self._native = None
        self.inserted = 0

    def clear(self) -> None:
        """Reset all native bits and insertion statistics."""
        self._native.clear()
        self.inserted = 0

    def estimated_false_positive_rate(self) -> float:
        """Estimate the current rate from add operations."""
        if self.inserted == 0:
            return 0.0
        return (
            1.0
            - math.exp(-self.hash_count * self.inserted / self.size)
        ) ** self.hash_count

    def get_hash_count(self) -> int:
        """Return the number of native probes per value."""
        return self.hash_count

    def get_indices(self, data: BloomValue) -> List[int]:
        """Return native XXH3 double-hash indices for Redis."""
        return list(self._native.get_hash_indices(_as_bytes(data)))


class BloomFilterFactory:
    """Select one backend once and construct API-compatible filters."""

    algorithm_name = "xxh3-km-v1"

    def __init__(
        self,
        importer: Importer = import_module,
    ) -> None:
        """Prefer fastbloom-rs and retain the portable implementation."""
        self._native_type = None
        try:
            module = importer("fastbloom_rs")
            native_type = getattr(module, "BloomFilter")
            if not callable(native_type):
                raise TypeError("fastbloom_rs.BloomFilter must be callable")
            self._native_type = native_type
        except ModuleNotFoundError as error:
            if error.name != "fastbloom_rs":
                logger.warning(
                    "fastbloom-rs could not load dependency %s; using Python fallback",
                    error.name,
                )
        except Exception as error:
            logger.warning(
                "fastbloom-rs is unavailable (%s: %s); using Python fallback",
                type(error).__name__,
                error,
            )

    @property
    def backend_name(self) -> str:
        """Return the selected backend identifier."""
        return "rust" if self._native_type is not None else "python"

    def create(
        self,
        size: int,
        expected: int,
        hash_count: int = 0,
    ) -> BloomFilterProtocol:
        """Construct one filter without a hot-path backend branch."""
        if self._native_type is not None:
            return RustBloomFilter(
                self._native_type,
                size=size,
                expected=expected,
                hash_count=hash_count,
            )
        return cast(
            BloomFilterProtocol,
            PythonBloomFilter(
                size=size,
                expected=expected,
                hash_count=hash_count,
            ),
        )


bloom_filter_factory = BloomFilterFactory()


__all__ = [
    "BloomFilterFactory",
    "BloomFilterProtocol",
    "BloomValue",
    "PythonBloomFilter",
    "RustBloomFilter",
    "bloom_filter_factory",
]
