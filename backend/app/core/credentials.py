import secrets
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.errors import fail


def load_master_key(path: str) -> bytes:
    try:
        key = Path(path).read_bytes()
    except OSError:
        fail(503, "CREDENTIAL_KEY_UNAVAILABLE", "Credential encryption is unavailable.")
    if len(key) != 32:
        fail(503, "CREDENTIAL_KEY_UNAVAILABLE", "Credential encryption is unavailable.")
    return key


def associated_data(workspace_id: uuid.UUID, connection_id: uuid.UUID, generation: int) -> bytes:
    return f"flowforge:v1:{workspace_id}:{connection_id}:{generation}".encode("ascii")


def encrypt_secret(
    key: bytes, workspace_id: uuid.UUID, connection_id: uuid.UUID, generation: int, secret: str
) -> tuple[bytes, bytes]:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(
        nonce, secret.encode("utf-8"), associated_data(workspace_id, connection_id, generation)
    )
    return nonce, ciphertext


def decrypt_secret(
    key: bytes,
    workspace_id: uuid.UUID,
    connection_id: uuid.UUID,
    generation: int,
    nonce: bytes,
    ciphertext: bytes,
) -> str:
    return (
        AESGCM(key)
        .decrypt(nonce, ciphertext, associated_data(workspace_id, connection_id, generation))
        .decode("utf-8")
    )
