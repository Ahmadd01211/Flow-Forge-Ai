"""Create local development secrets once, without printing their values."""
from pathlib import Path
import secrets
import os


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    target = root / ".env"
    if target.exists():
        print("Existing .env preserved.")
    else:
        target.write_text(
            f"POSTGRES_PASSWORD={secrets.token_hex(24)}\n"
            f"APP_DB_PASSWORD={secrets.token_hex(24)}\n"
            f"SESSION_SIGNING_KEY={secrets.token_hex(48)}\n"
            "PUBLIC_ORIGIN=http://localhost:8080\n",
            encoding="utf-8",
        )
        print("Local .env created. No secret values were printed.")
    key = root / ".local" / "secrets" / "credential-master.key"
    key.parent.mkdir(parents=True, exist_ok=True)
    if key.exists():
        print("Existing credential master key preserved.")
    else:
        descriptor = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(secrets.token_bytes(32))
        print("Local credential master key created outside the database.")


if __name__ == "__main__":
    main()
