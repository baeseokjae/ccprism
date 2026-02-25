import json
import os
import stat
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.auth.adapters.base import CredentialError
from src.auth.adapters.codex_oauth import CodexOAuthAdapter


@pytest.fixture
def auth_json_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with a valid auth.json."""
    auth_dir = tmp_path / ".codex"
    auth_dir.mkdir()
    return auth_dir


@pytest.fixture
def valid_token_data() -> dict:
    return {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "expires_at": time.time() + 3600,
        "api_base": "https://api.openai.com/v1",
        "org_id": "org-test123",
    }


@pytest.fixture
def expired_token_data() -> dict:
    return {
        "access_token": "expired-token",
        "refresh_token": "test-refresh-token",
        "expires_at": time.time() - 100,
    }


def write_auth_json(auth_dir: Path, data: dict) -> Path:
    auth_file = auth_dir / "auth.json"
    auth_file.write_text(json.dumps(data))
    os.chmod(auth_file, stat.S_IRUSR | stat.S_IWUSR)
    return auth_file


class TestReadAuthJson:
    def test_valid_file(self, auth_json_dir: Path, valid_token_data: dict) -> None:
        auth_file = write_auth_json(auth_json_dir, valid_token_data)
        adapter = CodexOAuthAdapter(auth_json_path=str(auth_file))

        result = adapter._read_auth_json()
        assert result is not None
        assert result["access_token"] == "test-access-token"
        assert result["refresh_token"] == "test-refresh-token"

    def test_missing_file(self, tmp_path: Path) -> None:
        adapter = CodexOAuthAdapter(auth_json_path=str(tmp_path / "nonexistent" / "auth.json"))
        result = adapter._read_auth_json()
        assert result is None

    def test_retry_on_json_decode_error(self, auth_json_dir: Path, valid_token_data: dict) -> None:
        auth_file = auth_json_dir / "auth.json"
        # Write invalid JSON first
        auth_file.write_text("{invalid json")
        os.chmod(auth_file, stat.S_IRUSR | stat.S_IWUSR)

        adapter = CodexOAuthAdapter(auth_json_path=str(auth_file))
        # All retries fail with invalid JSON
        result = adapter._read_auth_json()
        assert result is None  # No cached data, returns None

    def test_mtime_caching(self, auth_json_dir: Path, valid_token_data: dict) -> None:
        auth_file = write_auth_json(auth_json_dir, valid_token_data)
        adapter = CodexOAuthAdapter(auth_json_path=str(auth_file))

        # First read populates cache
        result1 = adapter._read_auth_json()
        assert result1 is not None

        # Second read should use cache (same mtime)
        result2 = adapter._read_auth_json()
        assert result2 == result1

    def test_warns_on_wrong_permissions(self, auth_json_dir: Path, valid_token_data: dict) -> None:
        auth_file = auth_json_dir / "auth.json"
        auth_file.write_text(json.dumps(valid_token_data))
        os.chmod(auth_file, 0o644)  # Wrong permissions

        adapter = CodexOAuthAdapter(auth_json_path=str(auth_file))
        # Should still read, but warn
        result = adapter._read_auth_json()
        assert result is not None


class TestGetCredentials:
    async def test_valid_token(self, auth_json_dir: Path, valid_token_data: dict) -> None:
        auth_file = write_auth_json(auth_json_dir, valid_token_data)
        adapter = CodexOAuthAdapter(auth_json_path=str(auth_file))

        creds = await adapter.get_credentials()
        assert creds["api_key"] == "test-access-token"
        assert creds["api_base"] == "https://api.openai.com/v1"
        assert creds["extra_headers"]["OpenAI-Organization"] == "org-test123"

    async def test_missing_file_raises(self, tmp_path: Path) -> None:
        adapter = CodexOAuthAdapter(auth_json_path=str(tmp_path / "missing" / "auth.json"))
        with pytest.raises(CredentialError, match="Cannot read auth data"):
            await adapter.get_credentials()

    async def test_expired_token_triggers_refresh(
        self, auth_json_dir: Path, expired_token_data: dict
    ) -> None:
        auth_file = write_auth_json(auth_json_dir, expired_token_data)
        adapter = CodexOAuthAdapter(auth_json_path=str(auth_file))

        refreshed = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
        }

        mock_response = httpx.Response(
            200,
            json=refreshed,
            request=httpx.Request("POST", "https://auth.openai.com/oauth/token"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            creds = await adapter.get_credentials()
            assert creds["api_key"] == "new-access-token"

    async def test_refresh_400_raises_credential_error(
        self, auth_json_dir: Path, expired_token_data: dict
    ) -> None:
        auth_file = write_auth_json(auth_json_dir, expired_token_data)
        adapter = CodexOAuthAdapter(auth_json_path=str(auth_file))

        mock_response = httpx.Response(
            400,
            json={"error": "invalid_grant"},
            request=httpx.Request("POST", "https://auth.openai.com/oauth/token"),
        )

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(CredentialError, match="Token refresh rejected"),
        ):
            await adapter.get_credentials()

    async def test_no_refresh_token_skips_refresh(self, auth_json_dir: Path) -> None:
        data = {
            "access_token": "old-token",
            "expires_at": time.time() - 100,
            # No refresh_token
        }
        auth_file = write_auth_json(auth_json_dir, data)
        adapter = CodexOAuthAdapter(auth_json_path=str(auth_file))

        with pytest.raises(CredentialError, match="No refresh_token"):
            await adapter.get_credentials()
