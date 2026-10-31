import secrets

import pytest

from app.operations.backup_bundle import seal, unseal


def test_local_backup_encrypts_secrets_and_rejects_tampering():
    files = {"database.dump": b"test database", "environment.env": b"TEST_SECRET=private", "credential-master.key": secrets.token_bytes(32)}
    password = "a-long-test-backup-password"
    first, second = seal(files, password), seal(files, password)
    assert first != second and b"TEST_SECRET=private" not in first
    assert unseal(first, password) == files
    for bundle, key in [(first, "a-different-backup-password"), (first[:-1] + bytes([first[-1] ^ 1]), password), (b"not-a-backup", password)]:
        with pytest.raises(ValueError):
            unseal(bundle, key)
    with pytest.raises(ValueError):
        seal(files, "short")
    with pytest.raises(ValueError):
        seal({**files, "unexpected": b"file"}, password)
