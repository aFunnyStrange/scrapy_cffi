import math, secrets, time, hashlib
from typing import List, Union

def do_sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()

def create_uniqueId():
    origin_array = [int(time.time()), math.floor(secrets.randbits(32) / 4294967296 * 4294967296)]
    value = (origin_array[0] << 32) + origin_array[1]
    if value >= 2**63:
        value -= 2**64
    return str(value)

def do_otp(secret: str, counter: int=None, timestamp_10: int=None) -> str:
    try:
        import pyotp
        secret_clean = secret.replace(" ", "")
        if counter is not None:
            return pyotp.HOTP(secret_clean).at(counter)
        else:
            totp = pyotp.TOTP(secret_clean)
            if timestamp_10:
                return totp.at(timestamp_10)
            return totp.now()
    except ImportError as e:
        raise ImportError(
            "Missing pyotp dependencies. "
            "Please install: pip install pyotp"
        ) from e

def get_node(nodes: List[str], fingerprint: Union[str, bytes]) -> str:
    if not nodes:
        raise ValueError("nodes cannot be empty")
    if isinstance(fingerprint, str):
        fingerprint = fingerprint.encode("utf-8")
    if not isinstance(fingerprint, bytes):
        raise ValueError("fingerprint must Union[str, bytes]")

    # Pure-Python Jump Consistent Hash. Keeping this tiny implementation in the
    # framework avoids making Redis Cluster routing depend on an optional C
    # extension that may be unavailable on a developer or production machine.
    key = int.from_bytes(hashlib.md5(fingerprint).digest()[:8], "big")
    bucket = -1
    candidate = 0
    while candidate < len(nodes):
        bucket = candidate
        key = (key * 2862933555777941757 + 1) & 0xFFFFFFFFFFFFFFFF
        candidate = int((bucket + 1) * (1 << 31) / ((key >> 33) + 1))
    return nodes[bucket]
