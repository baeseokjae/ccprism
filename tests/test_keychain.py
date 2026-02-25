"""Tests for OS Keychain integration."""

from unittest.mock import MagicMock, patch

from src.auth.keychain import (
    SERVICE_NAME,
    delete_credential,
    is_keyring_available,
    retrieve_credential,
    store_credential,
)


class TestIsKeyringAvailable:
    def setup_method(self) -> None:
        # Reset the cached state before each test
        import src.auth.keychain as mod
        mod._keyring_available = None

    def test_available_with_real_backend(self) -> None:
        mock_backend = MagicMock()
        with patch("keyring.get_keyring", return_value=mock_backend):
            assert is_keyring_available() is True

    def test_unavailable_with_fail_backend(self) -> None:
        from keyring.backends.fail import Keyring as FailKeyring

        mock_backend = FailKeyring()
        with patch("keyring.get_keyring", return_value=mock_backend):
            assert is_keyring_available() is False

    def test_unavailable_on_import_error(self) -> None:
        with patch("keyring.get_keyring", side_effect=Exception("no backend")):
            assert is_keyring_available() is False

    def test_caches_result(self) -> None:
        import src.auth.keychain as mod

        mod._keyring_available = True
        # Should return cached value without calling keyring
        assert is_keyring_available() is True


class TestStoreCredential:
    def setup_method(self) -> None:
        import src.auth.keychain as mod
        mod._keyring_available = None

    def test_stores_when_available(self) -> None:
        with patch("src.auth.keychain.is_keyring_available", return_value=True), \
             patch("keyring.set_password") as mock_set:
            result = store_credential("OPENAI_API_KEY", "sk-test123")
            assert result is True
            mock_set.assert_called_once_with(SERVICE_NAME, "OPENAI_API_KEY", "sk-test123")

    def test_returns_false_when_unavailable(self) -> None:
        with patch("src.auth.keychain.is_keyring_available", return_value=False):
            result = store_credential("key", "value")
            assert result is False

    def test_returns_false_on_exception(self) -> None:
        with patch("src.auth.keychain.is_keyring_available", return_value=True), \
             patch("keyring.set_password", side_effect=Exception("denied")):
            result = store_credential("key", "value")
            assert result is False


class TestRetrieveCredential:
    def setup_method(self) -> None:
        import src.auth.keychain as mod
        mod._keyring_available = None

    def test_retrieves_when_available(self) -> None:
        with patch("src.auth.keychain.is_keyring_available", return_value=True), \
             patch("keyring.get_password", return_value="sk-secret"):
            result = retrieve_credential("OPENAI_API_KEY")
            assert result == "sk-secret"

    def test_returns_none_when_not_found(self) -> None:
        with patch("src.auth.keychain.is_keyring_available", return_value=True), \
             patch("keyring.get_password", return_value=None):
            result = retrieve_credential("MISSING_KEY")
            assert result is None

    def test_returns_none_when_unavailable(self) -> None:
        with patch("src.auth.keychain.is_keyring_available", return_value=False):
            result = retrieve_credential("key")
            assert result is None

    def test_returns_none_on_exception(self) -> None:
        with patch("src.auth.keychain.is_keyring_available", return_value=True), \
             patch("keyring.get_password", side_effect=Exception("denied")):
            result = retrieve_credential("key")
            assert result is None


class TestDeleteCredential:
    def setup_method(self) -> None:
        import src.auth.keychain as mod
        mod._keyring_available = None

    def test_deletes_when_available(self) -> None:
        with patch("src.auth.keychain.is_keyring_available", return_value=True), \
             patch("keyring.delete_password") as mock_del:
            result = delete_credential("OLD_KEY")
            assert result is True
            mock_del.assert_called_once_with(SERVICE_NAME, "OLD_KEY")

    def test_returns_false_when_unavailable(self) -> None:
        with patch("src.auth.keychain.is_keyring_available", return_value=False):
            result = delete_credential("key")
            assert result is False

    def test_returns_false_on_not_found(self) -> None:
        import keyring.errors

        with patch("src.auth.keychain.is_keyring_available", return_value=True), \
             patch("keyring.delete_password", side_effect=keyring.errors.PasswordDeleteError()):
            result = delete_credential("MISSING")
            assert result is False
