"""Encrypted local provider credentials; never serialized into job definitions."""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from quantlab.data.providers.factory import provider_status

PROVIDER_KEYS = {
    "alpaca": ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"),
    "databento": ("DATABENTO_API_KEY",),
}


class ProviderKeyStore:
    def __init__(self, directory):
        self.directory = Path(directory)

    @contextmanager
    def locked(self):
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.directory.chmod(0o700)
        path = self.directory / "store.lock"
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a+b") as handle:
            os.fchmod(handle.fileno(), 0o600)
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def cipher(self):
        key = os.getenv("QUANTLAB_CREDENTIALS_MASTER_KEY")
        if not key:
            path = self.directory / "master.key"
            if not path.exists():
                if (self.directory / "providers.enc").exists():
                    raise ValueError(
                        "Credential encryption key is missing; restore the original key"
                    )
                descriptor = os.open(
                    path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
                )
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(Fernet.generate_key())
                    handle.flush()
                    os.fsync(handle.fileno())
            if path.is_symlink():
                raise ValueError("Credential encryption key must be a private regular file")
            path.chmod(0o600)
            key = path.read_bytes()
        try:
            return Fernet(key)
        except (ValueError, TypeError):
            raise ValueError("Credential encryption key configuration is invalid") from None

    def read(self):
        path = self.directory / "providers.enc"
        if not path.exists():
            return {}
        if path.is_symlink():
            raise ValueError("Credential store must be a private regular file")
        try:
            return json.loads(self.cipher().decrypt(path.read_bytes()))
        except (InvalidToken, ValueError, TypeError):
            raise ValueError(
                "Credential store cannot be decrypted; restore its original key"
            ) from None

    def write(self, values):
        ciphertext = self.cipher().encrypt(json.dumps(values).encode())
        descriptor, name = tempfile.mkstemp(prefix=".pending-", dir=self.directory)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(ciphertext)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.directory / "providers.enc")
        finally:
            Path(name).unlink(missing_ok=True)

    def save(self, provider, values):
        if provider not in PROVIDER_KEYS or set(values) != set(PROVIDER_KEYS[provider]):
            raise ValueError("Invalid provider credential fields")
        if any(
            not isinstance(v, str)
            or not 8 <= len(v) <= 512
            or any(ord(c) < 33 or ord(c) > 126 for c in v)
            for v in values.values()
        ):
            raise ValueError("Provider keys must contain 8–512 printable characters without spaces")
        with self.locked():
            stored = self.read()
            stored[provider] = values
            self.write(stored)

    def remove(self, provider):
        if provider not in PROVIDER_KEYS:
            raise ValueError("Unknown credential provider")
        with self.locked():
            stored = self.read()
            stored.pop(provider, None)
            self.write(stored)

    def credentials(self, provider):
        if provider not in PROVIDER_KEYS:
            raise ValueError("Unknown credential provider")
        with self.locked():
            stored = self.read()
        # A stored Alpaca pair always overrides the entire environment pair together.
        if provider in stored:
            return dict(stored[provider])
        return {key: os.environ[key] for key in PROVIDER_KEYS[provider] if os.getenv(key)}

    def status(self):
        with self.locked():
            stored = self.read()
        effective = {
            key: value
            for provider, keys in PROVIDER_KEYS.items()
            for key, value in (
                stored[provider] if provider in stored else {k: os.getenv(k, "") for k in keys}
            ).items()
        }
        result = provider_status(effective)
        for item in result["items"]:
            saved = item["id"] in stored
            item.update(
                {
                    "saved": saved,
                    "source": "dashboard"
                    if saved
                    else "environment"
                    if item["configured"]
                    else "none",
                }
            )
        return result
