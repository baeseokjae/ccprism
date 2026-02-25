from .base import BaseAuthAdapter


class NoAuthAdapter(BaseAuthAdapter):
    """No authentication needed (e.g., local Ollama)."""

    async def get_credentials(self) -> dict:
        return {}
