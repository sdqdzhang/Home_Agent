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
