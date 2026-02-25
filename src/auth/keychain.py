"""OS Keychain integration using the keyring library.

Provides a unified interface for storing/retrieving credentials across platforms:
- macOS: Keychain
- Linux: SecretService / KWallet
- Windows: Windows Credential Locker
"""

import logging

logger = logging.getLogger("ccprism.auth.keychain")

SERVICE_NAME = "ccprism"

_keyring_available: bool | None = None


def is_keyring_available() -> bool:
    """Check if a usable keyring backend is available."""
    global _keyring_available
    if _keyring_available is not None:
        return _keyring_available

    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        backend = keyring.get_keyring()
        if isinstance(backend, FailKeyring):
            logger.debug("Keyring backend is FailKeyring, not usable")
            _keyring_available = False
        else:
            logger.debug("Keyring backend: %s", type(backend).__name__)
            _keyring_available = True
    except Exception as e:
        logger.debug("Keyring not available: %s", e)
        _keyring_available = False

    return _keyring_available


def store_credential(key: str, value: str, service: str = SERVICE_NAME) -> bool:
    """Store a credential in the OS keychain.

    Returns True on success, False if keyring is not available.
    """
    if not is_keyring_available():
        return False

    try:
        import keyring

        keyring.set_password(service, key, value)
        logger.info("Stored credential '%s' in keychain", key)
        return True
    except Exception as e:
        logger.warning("Failed to store credential in keychain: %s", e)
        return False


def retrieve_credential(key: str, service: str = SERVICE_NAME) -> str | None:
    """Retrieve a credential from the OS keychain.

    Returns the value or None if not found or keyring unavailable.
    """
    if not is_keyring_available():
        return None

    try:
        import keyring

        value = keyring.get_password(service, key)
        if value is not None:
            logger.debug("Retrieved credential '%s' from keychain", key)
        return value
    except Exception as e:
        logger.warning("Failed to retrieve credential from keychain: %s", e)
        return None


def delete_credential(key: str, service: str = SERVICE_NAME) -> bool:
    """Delete a credential from the OS keychain.

    Returns True if deleted, False if not found or keyring unavailable.
    """
    if not is_keyring_available():
        return False

    try:
        import keyring

        keyring.delete_password(service, key)
        logger.info("Deleted credential '%s' from keychain", key)
        return True
    except keyring.errors.PasswordDeleteError:
        return False
    except Exception as e:
        logger.warning("Failed to delete credential from keychain: %s", e)
        return False
