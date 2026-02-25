import logging
import os
import time

from .base import BaseAuthAdapter

logger = logging.getLogger("ccprism.auth.google")


class GoogleOAuthAdapter(BaseAuthAdapter):
    """Google Vertex AI authentication via ADC or Service Account."""

    def __init__(self) -> None:
        self._credentials: dict | None = None
        self._expiry: float = 0

    async def get_credentials(self) -> dict:
        """Return Vertex AI credentials.

        Uses Application Default Credentials (ADC).
        """
        if self._credentials and time.time() < self._expiry - 300:
            return self._credentials

        try:
            import google.auth  # type: ignore[import-untyped]
            import google.auth.transport.requests  # type: ignore[import-untyped]

            creds, project = google.auth.default()
            request = google.auth.transport.requests.Request()
            creds.refresh(request)
            self._credentials = {
                "vertex_credentials": creds.token,
                "vertex_project": project,
            }
            self._expiry = creds.expiry.timestamp() if creds.expiry else time.time() + 3600
        except ImportError:
            logger.info("google-auth not installed, falling back to environment variables")
            self._credentials = {
                "vertex_credentials": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""),
                "vertex_project": os.environ.get("GCP_PROJECT", ""),
            }
            self._expiry = time.time() + 3600

        return self._credentials
