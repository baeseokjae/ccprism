import json
import logging
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("ccprism.auth.vault")

_KDF_ITERATIONS = 100_000
_SALT_SIZE = 16
_NONCE_SIZE = 12


class CredentialVault:
    """Encrypted credential store using AES-256-GCM with PBKDF2 key derivation."""

    def __init__(
        self,
        path: str = "~/.ccprism/credentials.enc",
        passphrase: str | None = None,
    ) -> None:
        self._path = Path(path).expanduser()
        self._passphrase = (passphrase or os.environ.get("CCPRISM_VAULT_PASSPHRASE", "")).encode()
        self._data: dict[str, str] = {}
        self._salt: bytes | None = None
        self._load()

    def _derive_key(self, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=_KDF_ITERATIONS,
        )
        return kdf.derive(self._passphrase)

    def _load(self) -> None:
        if not self._path.exists():
            self._data = {}
            return

        try:
            raw = self._path.read_bytes()
            if len(raw) < _SALT_SIZE + _NONCE_SIZE + 1:
                logger.warning("Vault file too small, starting fresh")
                self._data = {}
                return

            self._salt = raw[:_SALT_SIZE]
            nonce = raw[_SALT_SIZE : _SALT_SIZE + _NONCE_SIZE]
            ciphertext = raw[_SALT_SIZE + _NONCE_SIZE :]

            key = self._derive_key(self._salt)
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            self._data = json.loads(plaintext.decode("utf-8"))
        except Exception as e:
            logger.error("Failed to load vault: %s", e)
            self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        salt = self._salt or os.urandom(_SALT_SIZE)
        self._salt = salt
        nonce = os.urandom(_NONCE_SIZE)

        key = self._derive_key(salt)
        aesgcm = AESGCM(key)

        plaintext = json.dumps(self._data).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        self._path.write_bytes(salt + nonce + ciphertext)
        os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)

    def store(self, key: str, value: str) -> None:
        """Store a credential."""
        self._data[key] = value
        self._save()
        logger.info("Stored credential: %s", key)

    def retrieve(self, key: str) -> str | None:
        """Retrieve a credential by key."""
        return self._data.get(key)

    def delete(self, key: str) -> bool:
        """Delete a credential. Returns True if key existed."""
        if key in self._data:
            del self._data[key]
            self._save()
            logger.info("Deleted credential: %s", key)
            return True
        return False

    def list_keys(self) -> list[str]:
        """List all stored credential keys."""
        return list(self._data.keys())
