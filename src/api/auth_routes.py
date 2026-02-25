"""Auth API endpoints for ccprism gateway."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..auth.credential_manager import CredentialManager
from ..auth.oauth_server import OAuthServer, create_oauth_server

logger = logging.getLogger("ccprism.api.auth")

router = APIRouter(tags=["auth"])

# Module-level singletons (initialized on first use)
_oauth_server: OAuthServer | None = None
_credential_manager: CredentialManager | None = None


def get_oauth_server() -> OAuthServer:
    global _oauth_server
    if _oauth_server is None:
        _oauth_server = create_oauth_server()
    return _oauth_server


def get_credential_manager() -> CredentialManager:
    global _credential_manager
    if _credential_manager is None:
        _credential_manager = CredentialManager()
    return _credential_manager


# --- Request/Response Models ---


class TokenRequest(BaseModel):
    grant_type: str
    code: str | None = None
    redirect_uri: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    code_verifier: str | None = None
    refresh_token: str | None = None
    scope: str | None = None
    device_code: str | None = None


class DeviceCodeRequest(BaseModel):
    client_id: str
    scope: str = ""


class DeviceAuthorizeRequest(BaseModel):
    user_code: str
    user_id: str = "local_user"


# --- Endpoints ---


@router.post("/oauth/token")
async def token_endpoint(req: TokenRequest) -> dict:
    """OAuth 2.0 token endpoint."""
    server = get_oauth_server()

    if req.grant_type == "authorization_code":
        if not req.code or not req.client_id or not req.redirect_uri:
            raise HTTPException(400, "Missing required parameters for authorization_code grant")
        result = server.exchange_authorization_code(
            code=req.code,
            client_id=req.client_id,
            redirect_uri=req.redirect_uri,
            code_verifier=req.code_verifier,
        )
        if not result:
            raise HTTPException(400, "Invalid authorization code")
        return result

    elif req.grant_type == "client_credentials":
        if not req.client_id or not req.client_secret:
            raise HTTPException(400, "Missing client_id or client_secret")
        result = server.client_credentials_grant(
            client_id=req.client_id,
            client_secret=req.client_secret,
            scope=req.scope or "",
        )
        if not result:
            raise HTTPException(401, "Invalid client credentials")
        return result

    elif req.grant_type == "refresh_token":
        if not req.refresh_token or not req.client_id:
            raise HTTPException(400, "Missing refresh_token or client_id")
        result = server.refresh_access_token(
            refresh_token=req.refresh_token,
            client_id=req.client_id,
        )
        if not result:
            raise HTTPException(400, "Invalid refresh token")
        return result

    elif req.grant_type == "urn:ietf:params:oauth:grant-type:device_code":
        if not req.device_code or not req.client_id:
            raise HTTPException(400, "Missing device_code or client_id")
        result = server.poll_device_code(
            device_code=req.device_code,
            client_id=req.client_id,
        )
        if "error" in result:
            status = 400
            if result["error"] == "authorization_pending":
                status = 428
            elif result["error"] == "expired_token":
                status = 400
            raise HTTPException(status, detail=result)
        return result

    else:
        raise HTTPException(400, f"Unsupported grant_type: {req.grant_type}")


@router.get("/oauth/authorize")
async def authorize_endpoint(
    response_type: str = "code",
    client_id: str = "",
    redirect_uri: str = "",
    scope: str = "",
    state: str = "",
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
) -> dict:
    """OAuth 2.0 authorization endpoint.

    In production, this would render a consent UI. For now, auto-approves.
    """
    server = get_oauth_server()

    if not client_id:
        raise HTTPException(400, "Missing client_id")

    client = server.get_client(client_id)
    if not client:
        raise HTTPException(400, "Unknown client_id")

    code = server.create_authorization_code(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        user_id="local_user",
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )

    return {
        "code": code,
        "state": state,
        "redirect_uri": redirect_uri,
    }


@router.post("/oauth/device")
async def device_code_endpoint(req: DeviceCodeRequest) -> dict:
    """Device code flow initiation."""
    server = get_oauth_server()
    return server.create_device_code(client_id=req.client_id, scope=req.scope)


@router.post("/oauth/device/authorize")
async def device_authorize_endpoint(req: DeviceAuthorizeRequest) -> dict:
    """Authorize a device code (simulates user approval)."""
    server = get_oauth_server()
    success = server.authorize_device(user_code=req.user_code, user_id=req.user_id)
    if not success:
        raise HTTPException(400, "Invalid or expired user code")
    return {"status": "authorized"}


@router.get("/auth/status")
async def auth_status() -> dict:
    """Show auth status for all registered providers."""
    manager = get_credential_manager()
    status: dict[str, dict] = {}

    for provider, adapter in manager._adapters.items():
        try:
            creds = await adapter.get_credentials()
            status[provider] = {
                "status": "ok",
                "has_credentials": bool(creds),
            }
        except Exception as e:
            status[provider] = {
                "status": "error",
                "error": str(e),
            }

    return {"providers": status}
