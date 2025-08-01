import pyotp

def do_totp(secret: str, now_timestamp_10: int=0) -> str:
    totp = pyotp.TOTP(secret.replace(" ", ""))
    if now_timestamp_10:
        return totp.at(for_time=now_timestamp_10)
    return totp.now()