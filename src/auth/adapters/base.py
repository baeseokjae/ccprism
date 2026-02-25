from abc import ABC, abstractmethod


class CredentialError(Exception):
    """Raised when credentials cannot be obtained or are invalid."""

    pass


class BaseAuthAdapter(ABC):
    """Base class for all authentication adapters."""

    @abstractmethod
    async def get_credentials(self) -> dict:
        """Return credentials dict for the provider.

        Returns dict with keys like:
            api_key: str
            api_base: str (optional)
            extra_headers: dict (optional)
        """
        ...

    async def start_watcher(self) -> None:  # noqa: B027
        """Optional: start file/token watcher for auto-refresh."""

    async def close(self) -> None:  # noqa: B027
        """Cleanup resources."""
