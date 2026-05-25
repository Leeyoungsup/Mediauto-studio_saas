"""text text AES-256-GCM text/text text

text text: text, text text text text text text text
- AES-256-GCM: text + text text text
- text text text nonce text (text text)
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _get_aes_key() -> bytes:
    """text AES text text (32text = 256text)"""
    str_key = settings.FIELD_ENCRYPTION_KEY
    bytes_key = base64.urlsafe_b64decode(str_key + "==")
    # 32text text
    if len(bytes_key) < 32:
        bytes_key = bytes_key.ljust(32, b"\x00")
    return bytes_key[:32]


def encrypt_field(str_plaintext: str) -> str:
    """text → text (base64 text)

    text: base64(nonce + ciphertext + tag)
    """
    if not str_plaintext:
        return ""

    bytes_key = _get_aes_key()
    aesgcm = AESGCM(bytes_key)

    bytes_nonce = os.urandom(12)  # 96-bit nonce (GCM text)
    bytes_ciphertext = aesgcm.encrypt(
        bytes_nonce,
        str_plaintext.encode("utf-8"),
        None,
    )
    # nonce + ciphertext text text base64 text
    bytes_combined = bytes_nonce + bytes_ciphertext
    return base64.urlsafe_b64encode(bytes_combined).decode("ascii")


def decrypt_field(str_encrypted: str) -> str:
    """text → text"""
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
