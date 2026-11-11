"""Password-encrypted local backup envelope. No archive files are extracted to disk."""

import hashlib
import io
import json
import secrets
import zipfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"FLOWFORGE-BACKUP-1\x00"
MAX_BYTES = 256 * 1024 * 1024
FILES = {"database.dump", "environment.env", "credential-master.key"}


def _key(password: str, salt: bytes) -> bytes:
    if len(password) < 16 or len(password.encode()) > 4096:
        raise ValueError("Use a backup password with 16–4096 characters.")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode())


def seal(files: dict[str, bytes], password: str) -> bytes:
    if set(files) != FILES or len(files["credential-master.key"]) != 32:
        raise ValueError("A backup needs the database, environment and 32-byte credential key.")
    if sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError("This local backup supports at most 256 MiB. Use managed backup tooling for larger databases.")
    manifest = json.dumps({"format_version": 1, "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}, sort_keys=True).encode()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
        for name, data in {**files, "manifest.json": manifest}.items():
            output.writestr(name, data)
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    header = MAGIC + salt + nonce
    return header + AESGCM(_key(password, salt)).encrypt(nonce, archive.getvalue(), header)


def unseal(bundle: bytes, password: str) -> dict[str, bytes]:
    if len(bundle) > MAX_BYTES + 65536 or not bundle.startswith(MAGIC):
        raise ValueError("Invalid or oversized FlowForge backup.")
    size = len(MAGIC)
    salt, nonce = bundle[size:size+16], bundle[size+16:size+28]
    header = bundle[:size+28]
    try:
        plain = AESGCM(_key(password, salt)).decrypt(nonce, bundle[size+28:], header)
        with zipfile.ZipFile(io.BytesIO(plain)) as archive:
            names = archive.namelist()
            if len(names) != 4 or set(names) != FILES | {"manifest.json"}:
                raise ValueError("Unexpected backup entries.")
            if sum(item.file_size for item in archive.infolist()) > MAX_BYTES + 4096:
                raise ValueError("Oversized backup entries.")
            manifest = json.loads(archive.read("manifest.json"))
            files = {name: archive.read(name) for name in FILES}
        if manifest != {"format_version": 1, "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}} or len(files["credential-master.key"]) != 32:
            raise ValueError("Backup integrity check failed.")
        return files
    except Exception:
        raise ValueError("Could not unlock or verify this backup. Check the password and file integrity.") from None
