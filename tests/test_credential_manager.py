import pytest

from src.auth.adapters.base import BaseAuthAdapter, CredentialError
from src.auth.credential_manager import CredentialManager


class DummyAdapter(BaseAuthAdapter):
    async def get_credentials(self) -> dict:
        return {"api_key": "test-key-123"}


class FailingAdapter(BaseAuthAdapter):
    async def get_credentials(self) -> dict:
        raise CredentialError("intentional failure")


class TestCredentialManager:
    def setup_method(self) -> None:
        self.manager = CredentialManager()

    async def test_register_adapter(self) -> None:
        adapter = DummyAdapter()
        self.manager.register_adapter("custom_provider", adapter)
        creds = await self.manager.get_credentials("custom_provider")
        assert creds == {"api_key": "test-key-123"}

    async def test_get_credentials_known_provider(self) -> None:
        """Known providers should have adapters registered by default."""
        # ollama uses NoAuthAdapter which always returns {}
        creds = await self.manager.get_credentials("ollama")
        assert creds == {}

    async def test_get_credentials_unknown_provider_raises(self) -> None:
        with pytest.raises(CredentialError, match="No adapter registered"):
            await self.manager.get_credentials("nonexistent_provider")

    async def test_register_overrides_existing(self) -> None:
        adapter = DummyAdapter()
        self.manager.register_adapter("ollama", adapter)
        creds = await self.manager.get_credentials("ollama")
        assert creds == {"api_key": "test-key-123"}

    async def test_close_all(self) -> None:
        """close_all should not raise even with default adapters."""
        await self.manager.close_all()

    async def test_default_providers_registered(self) -> None:
        """All expected default providers should be registered."""
        expected = [
            "openai_codex", "google_vertex", "anthropic", "openai",
            "deepseek", "xai", "groq", "together", "ollama",
        ]
        for provider in expected:
            assert provider in self.manager._adapters
