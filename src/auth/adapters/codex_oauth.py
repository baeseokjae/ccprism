import asyncio
import contextlib
import json
import logging
import os
import stat
import time
from pathlib import Path

import httpx

from .base import BaseAuthAdapter, CredentialError

logger = logging.getLogger("ccprism.auth.codex")

_OPENAI_AUTH_URL = "https://auth.openai.com/oauth/token"
_OPENAI_CLIENT_ID = "app_sZnEaUhFxBqgNvar2gPOOdVz"


class CodexOAuthAdapter(BaseAuthAdapter):
    """OAuth adapter for OpenAI Codex CLI auth.json tokens."""

    def __init__(
        self,
        auth_json_path: str = "~/.codex/auth.json",
        auto_refresh: bool = True,
        refresh_before_expiry: int = 300,
    ) -> None:
        self._auth_path = Path(auth_json_path).expanduser()
        self._auto_refresh = auto_refresh
        self._refresh_before_expiry = refresh_before_expiry
        self._cached_data: dict | None = None
        self._cached_mtime: float = 0
        self._watcher_task: asyncio.Task | None = None  # type: ignore[type-arg]

    async def get_credentials(self) -> dict:
        token_data = self._read_auth_json()
        if not token_data:
            raise CredentialError(f"Cannot read auth data from {self._auth_path}")

        access_token = token_data.get("access_token", "")
        expires_at = token_data.get("expires_at", 0)

        # Refresh if expired or about to expire
        if time.time() > expires_at - self._refresh_before_expiry:
            if self._auto_refresh and token_data.get("refresh_token"):
                token_data = await self._refresh_token(token_data)
                access_token = token_data.get("access_token", access_token)
            elif not token_data.get("refresh_token"):
                raise CredentialError("No refresh_token available for expired token")

        result: dict = {
            "api_key": access_token,
        }

        api_base = token_data.get("api_base")
        if api_base:
            result["api_base"] = api_base

        org_id = token_data.get("org_id")
        if org_id:
            result["extra_headers"] = {"OpenAI-Organization": org_id}

        return result

    def _read_auth_json(self) -> dict | None:
        """Read and cache auth.json with mtime-based invalidation and retry logic."""
        if not self._auth_path.exists():
            logger.warning("Auth file not found: %s", self._auth_path)
            return self._cached_data

        # Check file permissions
        try:
            file_stat = self._auth_path.stat()
            mode = file_stat.st_mode & 0o777
            if mode != 0o600:
                logger.warning(
                    "Auth file %s has permissions %o, expected 0600",
                    self._auth_path,
                    mode,
                )

            # mtime-based caching
            if self._cached_data and file_stat.st_mtime == self._cached_mtime:
                return self._cached_data
        except OSError as e:
            logger.error("Cannot stat auth file: %s", e)
            return self._cached_data

        # Read with retry on parse errors
        delays = [0.1, 0.2, 0.4]
        for attempt, delay in enumerate(delays):
            try:
                raw = self._auth_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                self._cached_data = data
                self._cached_mtime = file_stat.st_mtime
                return data
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(
                    "Attempt %d: Failed to read auth.json: %s",
                    attempt + 1,
                    e,
                )
                if attempt < len(delays) - 1:
                    time.sleep(delay)

        logger.error("All retries exhausted reading %s, returning cached data", self._auth_path)
        return self._cached_data

    async def _refresh_token(self, token_data: dict) -> dict:
        """Refresh the OAuth token using the refresh_token."""
        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            raise CredentialError("No refresh_token available")

        delays = [1.0, 2.0]
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        _OPENAI_AUTH_URL,
                        json={
                            "grant_type": "refresh_token",
                            "refresh_token": refresh_token,
                            "client_id": _OPENAI_CLIENT_ID,
                        },
                    )

                    if resp.status_code in (400, 401):
                        raise CredentialError(
                            f"Token refresh rejected (HTTP {resp.status_code}): {resp.text}"
                        )

                    resp.raise_for_status()
                    new_tokens = resp.json()

                    # Merge new tokens into existing data
                    updated = {**token_data, **new_tokens}
                    if "expires_in" in new_tokens and "expires_at" not in new_tokens:
                        updated["expires_at"] = time.time() + new_tokens["expires_in"]

                    # Write back to auth.json
                    try:
                        self._auth_path.write_text(
                            json.dumps(updated, indent=2), encoding="utf-8"
                        )
                        os.chmod(self._auth_path, stat.S_IRUSR | stat.S_IWUSR)
                        self._cached_data = updated
                        self._cached_mtime = self._auth_path.stat().st_mtime
                    except OSError as e:
                        logger.error("Failed to write updated tokens: %s", e)

                    return updated

            except CredentialError:
                raise
            except Exception as e:
                last_error = e
                logger.warning("Token refresh attempt %d failed: %s", attempt + 1, e)
                if attempt < len(delays):
                    await asyncio.sleep(delays[attempt])

        logger.critical(
            "All token refresh attempts failed: %s. Returning expired token.", last_error
        )
        return token_data

    async def start_watcher(self) -> None:
        """Watch auth.json for changes and invalidate cache."""
        if self._watcher_task is not None:
            return

        self._watcher_task = asyncio.create_task(self._watch_loop())

    async def _watch_loop(self) -> None:
        try:
            from watchfiles import awatch

            watch_dir = self._auth_path.parent
            if not watch_dir.exists():
                logger.info("Watch directory does not exist: %s", watch_dir)
                return

            async for changes in awatch(watch_dir):
                for _change_type, path in changes:
                    if Path(path) == self._auth_path:
                        logger.debug("Auth file changed, invalidating cache")
                        self._cached_mtime = 0
        except ImportError:
            logger.info("watchfiles not installed, file watching disabled")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Watcher error: %s", e)

    async def close(self) -> None:
        if self._watcher_task is not None:
            self._watcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watcher_task
            self._watcher_task = None
