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

def do_totp(secret: str, counter: int=None, timestamp_10: int=None) -> str:
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
    try:
        import jump
        if isinstance(fingerprint, str):
            fingerprint = fingerprint.encode("utf-8")
        if not isinstance(fingerprint, bytes):
            raise ValueError("fingerprint must Union[str, bytes]")
        key_int = int(hashlib.md5(fingerprint).hexdigest(), 16)
        idx = jump.hash(key_int, len(nodes))
        return nodes[idx]
    except ImportError as e:
        raise ImportError(
            "Missing jump dependencies. "
            "Please install: pip install jump-consistent-hash"
        ) from e