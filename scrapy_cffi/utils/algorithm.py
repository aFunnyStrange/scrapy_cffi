import math, secrets, time, hashlib
from typing import List

def create_uniqueId():
    origin_array = [int(time.time()), math.floor(secrets.randbits(32) / 4294967296 * 4294967296)]
    value = (origin_array[0] << 32) + origin_array[1]
    if value >= 2**63:
        value -= 2**64
    return str(value)

def do_totp(secret: str, now_timestamp_10: int=0) -> str:
    try:
        import pyotp
        totp = pyotp.TOTP(secret.replace(" ", ""))
        if now_timestamp_10:
            return totp.at(for_time=now_timestamp_10)
        return totp.now()
    except ImportError as e:
        raise ImportError(
            "Missing pyotp dependencies. "
            "Please install: pip install pyotp"
        ) from e

def get_node(nodes: List[str], fingerprint: str) -> str:
    try:
        import jump
        key_int = int(hashlib.md5(fingerprint.encode('utf-8')).hexdigest(), 16)
        idx = jump.hash(key_int, len(nodes))
        return nodes[idx]
    except ImportError as e:
        raise ImportError(
            "Missing jump dependencies. "
            "Please install: pip install jump-consistent-hash"
        ) from e