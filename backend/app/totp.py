"""TOTP (Time-based One-Time Password) 2text text

pyotp text text text text — text text text.
RFC 6238 TOTP (HMAC-SHA1, 6text, 30text step).
"""

import base64
import hashlib
import hmac
import os
import struct
import time
from typing import Optional


def generate_totp_secret() -> str:
    """16text text text text → base32 text."""
    return base64.b32encode(os.urandom(16)).decode("ascii").rstrip("=")


def _hotp(bytes_secret: bytes, int_counter: int) -> str:
    """HOTP text (RFC 4226)."""
    bytes_counter = struct.pack(">Q", int_counter)
    bytes_hmac = hmac.new(bytes_secret, bytes_counter, hashlib.sha1).digest()
    int_offset = bytes_hmac[-1] & 0x0F
    int_code = (
        struct.unpack(">I", bytes_hmac[int_offset:int_offset + 4])[0] & 0x7FFFFFFF
    )
    return str(int_code % 1_000_000).zfill(6)


def get_totp_code(str_secret: str, int_time: Optional[int] = None) -> str:
    """text TOTP text text."""
    if int_time is None:
        int_time = int(time.time())
    # base32 text (text text)
    str_padded = str_secret + "=" * (-len(str_secret) % 8)
    bytes_secret = base64.b32decode(str_padded.upper())
    int_counter = int_time // 30
    return _hotp(bytes_secret, int_counter)


def verify_totp(str_secret: str, str_code: str, int_window: int = 1) -> bool:
    """TOTP text text (±window step text).

    int_window=1 text text + text 30text = text 90text text text.
    """
    int_now = int(time.time())
    str_padded = str_secret + "=" * (-len(str_secret) % 8)
    bytes_secret = base64.b32decode(str_padded.upper())
    int_counter = int_now // 30
    for int_offset in range(-int_window, int_window + 1):
        if _hotp(bytes_secret, int_counter + int_offset) == str_code:
            return True
    return False


def build_totp_uri(str_secret: str, str_account: str, str_issuer: str = "MeDIAuto Studio") -> str:
    """Google Authenticator text otpauth:// URI."""
    from urllib.parse import quote
    return (
        f"otpauth://totp/{quote(str_issuer)}:{quote(str_account)}"
        f"?secret={str_secret}&issuer={quote(str_issuer)}&algorithm=SHA1&digits=6&period=30"
    )
