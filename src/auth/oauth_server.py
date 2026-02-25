"""OAuth 2.0 server implementation for ccprism gateway.

Supports:
- Authorization Code + PKCE grant
- Device Code grant
- Client Credentials grant
"""

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field

from authlib.jose import jwt

logger = logging.getLogger("ccprism.auth.oauth")

# Token expiry defaults
ACCESS_TOKEN_EXPIRY = 3600  # 1 hour
REFRESH_TOKEN_EXPIRY = 86400 * 30  # 30 days
DEVICE_CODE_EXPIRY = 600  # 10 minutes
DEVICE_CODE_INTERVAL = 5  # polling interval in seconds


@dataclass
class OAuthClient:
    client_id: str
    client_secret: str | None = None
    redirect_uris: list[str] = field(default_factory=list)
    grant_types: list[str] = field(default_factory=lambda: ["authorization_code"])
    scope: str = ""


@dataclass
class AuthorizationCode:
    code: str
    client_id: str
    redirect_uri: str
    scope: str
    user_id: str
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    expires_at: float = 0


@dataclass
class DeviceCode:
    device_code: str
    user_code: str
    client_id: str
    scope: str
    expires_at: float = 0
    interval: int = DEVICE_CODE_INTERVAL
    authorized: bool = False
    user_id: str | None = None


class OAuthServer:
    """In-memory OAuth 2.0 server for development and single-node deployments."""

    def __init__(self, jwt_secret: str) -> None:
        self._jwt_secret = jwt_secret
        self._clients: dict[str, OAuthClient] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._device_codes: dict[str, DeviceCode] = {}
        self._refresh_tokens: dict[str, dict] = {}

    def register_client(self, client: OAuthClient) -> None:
        self._clients[client.client_id] = client

    def get_client(self, client_id: str) -> OAuthClient | None:
        return self._clients.get(client_id)

    # --- Authorization Code + PKCE ---

    def create_authorization_code(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str,
        user_id: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> str:
        code = secrets.token_urlsafe(32)
        self._auth_codes[code] = AuthorizationCode(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            user_id=user_id,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            expires_at=time.time() + 600,
        )
        return code

    def exchange_authorization_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> dict | None:
        auth_code = self._auth_codes.pop(code, None)
        if not auth_code:
            return None
        if auth_code.expires_at < time.time():
            return None
        if auth_code.client_id != client_id:
            return None
        if auth_code.redirect_uri != redirect_uri:
            return None

        # PKCE verification
        if auth_code.code_challenge:
            if not code_verifier:
                return None
            if auth_code.code_challenge_method == "S256":
                import base64

                expected = base64.urlsafe_b64encode(
                    hashlib.sha256(code_verifier.encode()).digest()
                ).rstrip(b"=").decode()
                if expected != auth_code.code_challenge:
                    return None
            elif auth_code.code_challenge != code_verifier:
                return None

        return self._issue_tokens(auth_code.user_id, auth_code.scope, client_id)

    # --- Device Code Flow ---

    def create_device_code(self, client_id: str, scope: str) -> dict:
        device_code = secrets.token_urlsafe(32)
        user_code = secrets.token_hex(3).upper()  # 6-char hex

        dc = DeviceCode(
            device_code=device_code,
            user_code=user_code,
            client_id=client_id,
            scope=scope,
            expires_at=time.time() + DEVICE_CODE_EXPIRY,
            interval=DEVICE_CODE_INTERVAL,
        )
        self._device_codes[device_code] = dc

        return {
            "device_code": device_code,
            "user_code": user_code,
            "expires_in": DEVICE_CODE_EXPIRY,
            "interval": DEVICE_CODE_INTERVAL,
        }

    def authorize_device(self, user_code: str, user_id: str) -> bool:
        for dc in self._device_codes.values():
            if dc.user_code == user_code and dc.expires_at > time.time():
                dc.authorized = True
                dc.user_id = user_id
                return True
        return False

    def poll_device_code(self, device_code: str, client_id: str) -> dict:
        dc = self._device_codes.get(device_code)
        if not dc:
            return {"error": "invalid_grant"}
        if dc.expires_at < time.time():
            self._device_codes.pop(device_code, None)
            return {"error": "expired_token"}
        if dc.client_id != client_id:
            return {"error": "invalid_client"}
        if not dc.authorized:
            return {"error": "authorization_pending"}

        self._device_codes.pop(device_code, None)
        return self._issue_tokens(dc.user_id or "device_user", dc.scope, client_id)

    # --- Client Credentials ---

    def client_credentials_grant(
        self, client_id: str, client_secret: str, scope: str
    ) -> dict | None:
        client = self._clients.get(client_id)
        if not client:
            return None
        if client.client_secret != client_secret:
            return None
        if "client_credentials" not in client.grant_types:
            return None

        return self._issue_tokens(f"client:{client_id}", scope, client_id)

    # --- Token Management ---

    def _issue_tokens(self, user_id: str, scope: str, client_id: str) -> dict:
        now = time.time()

        access_payload = {
            "sub": user_id,
            "scope": scope,
            "client_id": client_id,
            "iat": int(now),
            "exp": int(now + ACCESS_TOKEN_EXPIRY),
            "role": "user",
        }
        access_token = jwt.encode(
            {"alg": "HS256"}, access_payload, self._jwt_secret
        ).decode()

        refresh_token = secrets.token_urlsafe(48)
        self._refresh_tokens[refresh_token] = {
            "user_id": user_id,
            "scope": scope,
            "client_id": client_id,
            "expires_at": now + REFRESH_TOKEN_EXPIRY,
        }

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_EXPIRY,
            "refresh_token": refresh_token,
            "scope": scope,
        }

    def refresh_access_token(self, refresh_token: str, client_id: str) -> dict | None:
        token_data = self._refresh_tokens.get(refresh_token)
        if not token_data:
            return None
        if token_data["expires_at"] < time.time():
            self._refresh_tokens.pop(refresh_token, None)
            return None
        if token_data["client_id"] != client_id:
            return None

        # Rotate refresh token
        self._refresh_tokens.pop(refresh_token)
        return self._issue_tokens(token_data["user_id"], token_data["scope"], client_id)


def create_oauth_server(jwt_secret: str | None = None) -> OAuthServer:
    """Create an OAuth server instance."""
    from ..config import get_settings

    secret = jwt_secret or get_settings().jwt_secret_key or secrets.token_urlsafe(32)
    return OAuthServer(jwt_secret=secret)
