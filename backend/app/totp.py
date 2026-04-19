"""TOTP (Time-based One-Time Password) 2차 인증

pyotp 라이브러리 대신 직접 구현 — 외부 의존성 최소화.
RFC 6238 TOTP (HMAC-SHA1, 6자리, 30초 step).
"""

import base64
import hashlib
import hmac
import os
import struct
import time
from typing import Optional


def generate_totp_secret() -> str:
    """16바이트 랜덤 시크릿 생성 → base32 인코딩."""
    return base64.b32encode(os.urandom(16)).decode("ascii").rstrip("=")


def _hotp(bytes_secret: bytes, int_counter: int) -> str:
    """HOTP 계산 (RFC 4226)."""
    bytes_counter = struct.pack(">Q", int_counter)
    bytes_hmac = hmac.new(bytes_secret, bytes_counter, hashlib.sha1).digest()
    int_offset = bytes_hmac[-1] & 0x0F
    int_code = (
        struct.unpack(">I", bytes_hmac[int_offset:int_offset + 4])[0] & 0x7FFFFFFF
    )
    return str(int_code % 1_000_000).zfill(6)


def get_totp_code(str_secret: str, int_time: Optional[int] = None) -> str:
    """현재 TOTP 코드 계산."""
    if int_time is None:
        int_time = int(time.time())
    # base32 디코딩 (패딩 복원)
    str_padded = str_secret + "=" * (-len(str_secret) % 8)
    bytes_secret = base64.b32decode(str_padded.upper())
    int_counter = int_time // 30
    return _hotp(bytes_secret, int_counter)


def verify_totp(str_secret: str, str_code: str, int_window: int = 1) -> bool:
    """TOTP 코드 검증 (±window step 허용).

    int_window=1 이면 현재 + 전후 30초 = 총 90초 범위 허용.
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
    """Google Authenticator 호환 otpauth:// URI."""
    from urllib.parse import quote
    return (
        f"otpauth://totp/{quote(str_issuer)}:{quote(str_account)}"
        f"?secret={str_secret}&issuer={quote(str_issuer)}&algorithm=SHA1&digits=6&period=30"
    )
