import logging
import os

from .base import BaseAuthAdapter, CredentialError

logger = logging.getLogger("ccprism.auth.api_key")


class APIKeyAdapter(BaseAuthAdapter):
    """API key adapter with fallback chain: env var -> keychain -> vault."""

    def __init__(self, env_var: str, api_base: str | None = None):
        self.env_var = env_var
        self.api_base = api_base

    async def get_credentials(self) -> dict:
        api_key = self._resolve_key()
        if not api_key:
            raise CredentialError(
                f"No API key found for {self.env_var}. "
                f"Set env var, or use: ccprism auth add <provider> --key <key> --store keychain|vault"
            )
        result: dict = {"api_key": api_key}
        if self.api_base:
            result["api_base"] = self.api_base
        return result

    def _resolve_key(self) -> str | None:
        """Try env var, then keychain, then vault."""
        # 1. Environment variable (highest priority)
        api_key = os.environ.get(self.env_var)
        if api_key:
            return api_key

        # 2. OS Keychain
        try:
            from ..keychain import retrieve_credential

            api_key = retrieve_credential(self.env_var)
            if api_key:
                logger.debug("Resolved %s from OS keychain", self.env_var)
                return api_key
        except Exception:
            pass

        # 3. Encrypted vault
        try:
            from ..vault import CredentialVault

            vault = CredentialVault()
            api_key = vault.retrieve(self.env_var)
            if api_key:
                logger.debug("Resolved %s from vault", self.env_var)
                return api_key
        except Exception:
            pass

        return None
