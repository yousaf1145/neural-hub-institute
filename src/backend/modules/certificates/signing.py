"""
Certificate signing in "local" mode.

Each certificate payload is hashed (SHA-256) and signed with a secret key (HMAC).
Anyone holding the payload + signature can ask this server to verify it, and any change
to the payload breaks the signature.

Blockchain mode (Polygon NFT + IPFS) plugs in later: see blockchain.py.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

SECRET_FILE = Path(__file__).resolve().parents[2] / "certificate_secret.key"


def _secret() -> bytes:
    env = os.environ.get("CERT_SIGNING_SECRET")
    if env:
        return env.encode()
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_hex(32))
    return SECRET_FILE.read_text().strip().encode()


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


def sign(digest: str) -> str:
    return hmac.new(_secret(), digest.encode(), hashlib.sha256).hexdigest()


def certificate_id_for(digest: str) -> str:
    return f"NH-{digest[:4].upper()}-{digest[4:8].upper()}-{digest[8:12].upper()}"


def encode_payload(payload: dict) -> str:
    return base64.urlsafe_b64encode(canonical(payload)).decode().rstrip("=")


def decode_payload(token: str) -> dict:
    padded = token + "=" * (-len(token) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode()))
