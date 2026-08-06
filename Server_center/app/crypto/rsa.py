import base64
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OAEP_PADDING = padding.OAEP(
    mgf=padding.MGF1(algorithm=hashes.SHA256()),
    algorithm=hashes.SHA256(),
    label=None,
)

RSA_OAEP_CHUNK_SIZE = 190
HYBRID_ALG = "RSA-OAEP+AES-256-GCM"


def generate_keypair(key_size: int = 2048) -> tuple[RSAPrivateKey, RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    return private_key, private_key.public_key()


def save_keypair(private_key: RSAPrivateKey, public_key: RSAPublicKey, keys_dir: Path) -> None:
    keys_dir.mkdir(parents=True, exist_ok=True)
    private_path = keys_dir / "server_private.pem"
    public_path = keys_dir / "server_public.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def load_private_key(keys_dir: Path) -> RSAPrivateKey:
    path = keys_dir / "server_private.pem"
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def load_public_key(keys_dir: Path) -> RSAPublicKey:
    path = keys_dir / "server_public.pem"
    return serialization.load_pem_public_key(path.read_bytes())


def load_public_key_from_pem(pem: str | bytes) -> RSAPublicKey:
    if isinstance(pem, str):
        pem = pem.encode()
    return serialization.load_pem_public_key(pem)


def public_key_to_pem(public_key: RSAPublicKey) -> str:
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def ensure_server_keys(keys_dir: Path, key_size: int = 2048) -> tuple[RSAPrivateKey, RSAPublicKey]:
    private_path = keys_dir / "server_private.pem"
    public_path = keys_dir / "server_public.pem"
    if private_path.exists() and public_path.exists():
        return load_private_key(keys_dir), load_public_key(keys_dir)
    private_key, public_key = generate_keypair(key_size)
    save_keypair(private_key, public_key, keys_dir)
    return private_key, public_key


def encrypt_bytes(data: bytes, public_key: RSAPublicKey) -> bytes:
    return public_key.encrypt(data, OAEP_PADDING)


def decrypt_bytes(data: bytes, private_key: RSAPrivateKey) -> bytes:
    return private_key.decrypt(data, OAEP_PADDING)


def encrypt_to_b64(data: bytes, public_key: RSAPublicKey) -> str:
    return base64.b64encode(encrypt_bytes(data, public_key)).decode()


def decrypt_from_b64(data_b64: str, private_key: RSAPrivateKey) -> bytes:
    return decrypt_bytes(base64.b64decode(data_b64), private_key)


def is_encrypted_payload(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("encrypted") or payload.get("encrypted_chunks"):
        return True
    if payload.get("ek") and payload.get("ct") and payload.get("iv"):
        return True
    return False


def encrypt_payload_b64(data: bytes, public_key: RSAPublicKey) -> dict[str, str | int]:
    """Hybrid RSA-OAEP + AES-256-GCM (preferred for all sizes)."""
    aes_key = os.urandom(32)
    iv = os.urandom(12)
    ct = AESGCM(aes_key).encrypt(iv, data, None)
    return {
        "v": 1,
        "alg": HYBRID_ALG,
        "ek": encrypt_to_b64(aes_key, public_key),
        "iv": base64.b64encode(iv).decode(),
        "ct": base64.b64encode(ct).decode(),
    }


def encrypt_payload_b64_legacy(data: bytes, public_key: RSAPublicKey) -> dict[str, str | list[str]]:
    if len(data) <= RSA_OAEP_CHUNK_SIZE:
        return {"encrypted": encrypt_to_b64(data, public_key)}
    return {
        "encrypted_chunks": [
            encrypt_to_b64(data[i : i + RSA_OAEP_CHUNK_SIZE], public_key)
            for i in range(0, len(data), RSA_OAEP_CHUNK_SIZE)
        ]
    }


def decrypt_payload_b64(payload: dict[str, Any], private_key: RSAPrivateKey) -> bytes:
    if payload.get("ek") and payload.get("ct") and payload.get("iv"):
        aes_key = decrypt_from_b64(str(payload["ek"]), private_key)
        iv = base64.b64decode(payload["iv"])
        ct = base64.b64decode(payload["ct"])
        return AESGCM(aes_key).decrypt(iv, ct, None)

    single = payload.get("encrypted")
    if single:
        return decrypt_from_b64(single, private_key)
    chunks = payload.get("encrypted_chunks")
    if chunks:
        return b"".join(decrypt_from_b64(chunk, private_key) for chunk in chunks)
    raise ValueError("encrypted payload missing")
