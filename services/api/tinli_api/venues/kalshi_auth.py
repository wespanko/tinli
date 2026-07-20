"""BYOK Kalshi request signing (M9).

Spec (https://docs.kalshi.com/getting_started/api_keys, read 2026-07-20):
sign the string  f"{timestamp_ms}{METHOD}{path}"  — path WITHOUT the query
string — with RSA-PSS (SHA256, MGF1-SHA256, salt length = digest length),
base64-encode, and send three headers: KALSHI-ACCESS-KEY (key id),
KALSHI-ACCESS-TIMESTAMP (the same ms timestamp), KALSHI-ACCESS-SIGNATURE.

BYOK doctrine: the user's OWN key, read from .env, never committed, never
proxied. Hosted read-only instances refuse keys outright — a shared box
must never hold anyone's credentials.
"""

import base64
import os
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

KEY_ID_ENV = "TINLI_KALSHI_KEY_ID"
KEY_PATH_ENV = "TINLI_KALSHI_PRIVATE_KEY_PATH"


def message(ts_ms: int, method: str, path: str) -> str:
    """The exact string Kalshi verifies. Query strings are excluded by spec;
    strip defensively rather than trusting every caller."""
    return f"{ts_ms}{method.upper()}{path.split('?', 1)[0]}"


class KalshiAuth:
    def __init__(self, key_id: str, private_key: RSAPrivateKey) -> None:
        self.key_id = key_id
        self._key = private_key

    @classmethod
    def from_env(cls) -> "KalshiAuth | None":
        """None (feature off) unless both env vars are set and valid.
        Read-only hosted mode refuses keys even if present."""
        if os.environ.get("TINLI_READONLY", "0") == "1":
            return None
        key_id = os.environ.get(KEY_ID_ENV)
        key_path = os.environ.get(KEY_PATH_ENV)
        if not key_id or not key_path:
            return None
        pem = Path(key_path).read_bytes()
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, RSAPrivateKey):
            raise ValueError(f"{KEY_PATH_ENV} must be an RSA private key (PEM)")
        return cls(key_id, key)

    def sign(self, ts_ms: int, method: str, path: str) -> str:
        sig = self._key.sign(
            message(ts_ms, method, path).encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode()

    def headers(self, method: str, path: str, ts_ms: int | None = None) -> dict[str, str]:
        ts = ts_ms if ts_ms is not None else int(time.time() * 1000)
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": str(ts),
            "KALSHI-ACCESS-SIGNATURE": self.sign(ts, method, path),
        }
