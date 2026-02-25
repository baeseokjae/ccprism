import logging

from .adapters.base import BaseAuthAdapter, CredentialError

logger = logging.getLogger("ccprism.auth.manager")


class CredentialManager:
    """Manages provider -> adapter mapping and credential retrieval."""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseAuthAdapter] = {}
        self._setup_default_adapters()

    def _setup_default_adapters(self) -> None:
        """Register default adapters for known providers."""
        from .adapters.api_key import APIKeyAdapter
        from .adapters.codex_oauth import CodexOAuthAdapter
        from .adapters.google_oauth import GoogleOAuthAdapter
        from .adapters.no_auth import NoAuthAdapter

        self._adapters = {
            "openai_codex": CodexOAuthAdapter(),
            "google_vertex": GoogleOAuthAdapter(),
            "anthropic": APIKeyAdapter(env_var="ANTHROPIC_API_KEY"),
            "openai": APIKeyAdapter(env_var="OPENAI_API_KEY"),
            "deepseek": APIKeyAdapter(env_var="DEEPSEEK_API_KEY"),
            "xai": APIKeyAdapter(env_var="XAI_API_KEY"),
            "groq": APIKeyAdapter(env_var="GROQ_API_KEY"),
            "together": APIKeyAdapter(env_var="TOGETHERAI_API_KEY"),
            "ollama": NoAuthAdapter(),
        }

    def register_adapter(self, provider: str, adapter: BaseAuthAdapter) -> None:
        self._adapters[provider] = adapter

    async def get_credentials(self, provider: str) -> dict:
        adapter = self._adapters.get(provider)
        if not adapter:
            raise CredentialError(f"No adapter registered for provider: {provider}")
        return await adapter.get_credentials()

    async def start_watchers(self) -> None:
        """Start all file watchers."""
        for adapter in self._adapters.values():
            await adapter.start_watcher()

    async def close_all(self) -> None:
        for adapter in self._adapters.values():
            await adapter.close()
