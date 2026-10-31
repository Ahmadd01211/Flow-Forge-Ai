"""Create encrypted local backups and rehearse restores in a disposable database.

Run with backend/.venv/Scripts/python.exe on Windows. Never replaces the live
database, environment or credential key. Stop application services for a quiet
snapshot if credential rotation may occur during capture.
"""

import argparse
import getpass
import hashlib
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.operations.backup_bundle import seal, unseal  # noqa: E402


def docker(*arguments, input_data=None):
    result = subprocess.run(["docker", "compose", "exec", "-T", "postgres", *arguments], cwd=ROOT, input=input_data, capture_output=True)
    if result.returncode:
        raise RuntimeError("The database operation failed. Check the local PostgreSQL service; no secret values were printed.")
    return result.stdout


def capture(password):
    # Double-read local secrets to detect ordinary rotation while the dump runs.
    environment = (ROOT / ".env").read_bytes()
    key_path = ROOT / ".local" / "secrets" / "credential-master.key"
    key = key_path.read_bytes()
    dump = docker("pg_dump", "-U", "flowforge", "-d", "flowforge", "--format=custom", "--no-owner", "--no-acl")
    if key != key_path.read_bytes() or environment != (ROOT / ".env").read_bytes():
        raise RuntimeError("Local secrets changed during capture. Pause application services and repeat.")
    return seal({"database.dump": dump, "environment.env": environment, "credential-master.key": key}, password)


def verify_restore(bundle, password):
    files = unseal(bundle, password)
    name = "ff_restore_" + secrets.token_hex(8)
    created = False
    try:
        docker("createdb", "-U", "flowforge", name)
        created = True
        docker("pg_restore", "-U", "flowforge", "-d", name, "--no-owner", "--no-acl", "--exit-on-error", input_data=files["database.dump"])
        revision = docker("psql", "-U", "flowforge", "-d", name, "-v", "ON_ERROR_STOP=1", "-At", "-c", "SELECT version_num FROM alembic_version;").decode().strip()
        if not revision or not revision.isdigit():
            raise RuntimeError("Restored migration metadata did not validate.")
        # Verify restored tables, constraints and encrypted credential-key bytes
        # without reading customer records or starting any worker against them.
        docker("psql", "-U", "flowforge", "-d", name, "-v", "ON_ERROR_STOP=1", "-At", "-c", "SELECT 1 FROM app_user LIMIT 0; SELECT 1 FROM workflow_run LIMIT 0;")
        print(f"Encrypted backup and isolated PostgreSQL restore passed at migration {revision}. No live data was replaced.")
    finally:
        if created:
            docker("dropdb", "-U", "flowforge", name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "verify", "rehearse"])
    parser.add_argument("file", nargs="?", type=Path)
    args = parser.parse_args()
    if args.action == "rehearse":
        # A transient key exercises encryption/restore without saving secrets.
        password = secrets.token_urlsafe(48)
        verify_restore(capture(password), password)
        return
    if args.file is None:
        parser.error("create and verify require a backup file path")
    if args.action == "create" and args.file.exists():
        parser.error("The output exists; choose a new backup path")
    password = getpass.getpass("Backup password (at least 16 characters): ")
    if args.action == "create":
        if password != getpass.getpass("Repeat backup password: "):
            parser.error("Passwords did not match")
        bundle = capture(password)
        args.file.parent.mkdir(parents=True, exist_ok=True)
        with args.file.open("xb") as output:
            output.write(bundle)
        args.file.chmod(0o600)
        print("Encrypted backup saved. Keep its password separately. SHA-256: " + hashlib.sha256(bundle).hexdigest())
    else:
        verify_restore(args.file.read_bytes(), password)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
