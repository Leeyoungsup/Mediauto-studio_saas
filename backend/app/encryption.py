"""text text AES-256-GCM text/text text

text text: text, text text text text text text text
- AES-256-GCM: text + text text text
- text text text nonce text (text text)
"""

import base64
import os
import json

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

ENCRYPTED_JSON_MARKER = "__mediauto_encrypted__"


def encrypt_json(value: dict) -> dict:
    """Encrypt structured clinical fields before writing either database copy."""
    if not isinstance(value, dict):
        raise TypeError("Clinical information must be a dictionary")
    return {ENCRYPTED_JSON_MARKER: "AES-256-GCM-v1",
            "ciphertext": encrypt_field(json.dumps(value, ensure_ascii=False, separators=(",", ":")))}


def decrypt_json(value: dict) -> dict:
    """Read legacy plaintext; never fall back to plaintext for a damaged envelope."""
    if ENCRYPTED_JSON_MARKER not in value:
        return value
    if value.get(ENCRYPTED_JSON_MARKER) != "AES-256-GCM-v1" or set(value) != {ENCRYPTED_JSON_MARKER, "ciphertext"}:
        raise ValueError("Invalid encrypted clinical information envelope")
    result = json.loads(decrypt_field(value["ciphertext"]))
    if not isinstance(result, dict):
        raise ValueError("Invalid decrypted clinical information")
    return result


def _get_aes_key() -> bytes:
    """text AES text text (32text = 256text)"""
    str_key = settings.FIELD_ENCRYPTION_KEY
    try:
        bytes_key = base64.b64decode(str_key + "=" * (-len(str_key) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("FIELD_ENCRYPTION_KEY must be a valid base64url 256-bit key") from exc
    if len(bytes_key) != 32:
        raise ValueError("FIELD_ENCRYPTION_KEY must decode to exactly 32 bytes")
    return bytes_key



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
