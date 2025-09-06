import math, secrets, time

def create_uniqueId():
    origin_array = [int(time.time()), math.floor(secrets.randbits(32) / 4294967296 * 4294967296)]
    value = (origin_array[0] << 32) + origin_array[1]
    if value >= 2**63:
        value -= 2**64
    return str(value)