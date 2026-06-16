import base64
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

OAEP_PADDING = padding.OAEP(
    mgf=padding.MGF1(algorithm=hashes.SHA256()),
    algorithm=hashes.SHA256(),
    label=None,
)

RSA_OAEP_CHUNK_SIZE = 190


def generate_keypair(key_size: int = 2048) -> tuple[RSAPrivateKey, RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    return private_key, private_key.public_key()


def save_keypair(private_key: RSAPrivateKey, public_key: RSAPublicKey, keys_dir: Path) -> None:
    keys_dir.mkdir(parents=True, exist_ok=True)
    (keys_dir / "client_private.pem").write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    (keys_dir / "client_public.pem").write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def ensure_client_keys(keys_dir: Path, key_size: int = 2048) -> tuple[RSAPrivateKey, RSAPublicKey]:
    private_path = keys_dir / "client_private.pem"
    public_path = keys_dir / "client_public.pem"
    if private_path.exists() and public_path.exists():
        private_key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
        public_key = serialization.load_pem_public_key(public_path.read_bytes())
        return private_key, public_key
    private_key, public_key = generate_keypair(key_size)
    save_keypair(private_key, public_key, keys_dir)
    return private_key, public_key


def public_key_to_pem(public_key: RSAPublicKey) -> str:
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def load_public_key_from_pem(pem: str | bytes) -> RSAPublicKey:
    if isinstance(pem, str):
        pem = pem.encode()
    return serialization.load_pem_public_key(pem)


def encrypt_to_b64(data: bytes, public_key: RSAPublicKey) -> str:
    cipher = public_key.encrypt(data, OAEP_PADDING)
    return base64.b64encode(cipher).decode()


def decrypt_from_b64(data_b64: str, private_key: RSAPrivateKey) -> bytes:
    return private_key.decrypt(base64.b64decode(data_b64), OAEP_PADDING)


def encrypt_payload_b64(data: bytes, public_key: RSAPublicKey) -> dict[str, str | list[str]]:
    if len(data) <= RSA_OAEP_CHUNK_SIZE:
        return {"encrypted": encrypt_to_b64(data, public_key)}
    return {
        "encrypted_chunks": [
            encrypt_to_b64(data[i : i + RSA_OAEP_CHUNK_SIZE], public_key)
            for i in range(0, len(data), RSA_OAEP_CHUNK_SIZE)
        ]
    }


def decrypt_payload_b64(payload: dict[str, str | list[str] | None], private_key: RSAPrivateKey) -> bytes:
    single = payload.get("encrypted")
    if single:
        return decrypt_from_b64(single, private_key)
    chunks = payload.get("encrypted_chunks")
    if chunks:
        return b"".join(decrypt_from_b64(chunk, private_key) for chunk in chunks)
    raise ValueError("encrypted payload missing")
