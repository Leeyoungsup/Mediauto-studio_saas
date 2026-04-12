"""민감 필드 AES-256-GCM 암호화/복호화 유틸리티

병원 환경: 환자명, 주민번호 등 민감 데이터를 필드 레벨에서 암호화
- AES-256-GCM: 인증 + 암호화 동시 제공
- 각 암호화마다 고유 nonce 사용 (재사용 방지)
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _get_aes_key() -> bytes:
    """설정에서 AES 키 추출 (32바이트 = 256비트)"""
    str_key = settings.FIELD_ENCRYPTION_KEY
    bytes_key = base64.urlsafe_b64decode(str_key + "==")
    # 32바이트로 맞춤
    if len(bytes_key) < 32:
        bytes_key = bytes_key.ljust(32, b"\x00")
    return bytes_key[:32]


def encrypt_field(str_plaintext: str) -> str:
    """평문 → 암호문 (base64 인코딩)

    형식: base64(nonce + ciphertext + tag)
    """
    if not str_plaintext:
        return ""

    bytes_key = _get_aes_key()
    aesgcm = AESGCM(bytes_key)

    bytes_nonce = os.urandom(12)  # 96-bit nonce (GCM 표준)
    bytes_ciphertext = aesgcm.encrypt(
        bytes_nonce,
        str_plaintext.encode("utf-8"),
        None,
    )
    # nonce + ciphertext 를 합쳐서 base64 인코딩
    bytes_combined = bytes_nonce + bytes_ciphertext
    return base64.urlsafe_b64encode(bytes_combined).decode("ascii")


def decrypt_field(str_encrypted: str) -> str:
    """암호문 → 평문"""
    if not str_encrypted:
        return ""

    bytes_key = _get_aes_key()
    aesgcm = AESGCM(bytes_key)

    bytes_combined = base64.urlsafe_b64decode(str_encrypted)
    bytes_nonce = bytes_combined[:12]
    bytes_ciphertext = bytes_combined[12:]

    bytes_plaintext = aesgcm.decrypt(
        bytes_nonce,
        bytes_ciphertext,
        None,
    )
    return bytes_plaintext.decode("utf-8")
