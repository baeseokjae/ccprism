"""Authentication and authorization for the gateway's HTTP boundary."""

from __future__ import annotations

import hmac
import ipaddress
import logging
import math
from typing import Annotated, Any

from authlib.jose import JsonWebToken
from fastapi import Depends, HTTPException, Request

from ..config import GatewaySettings, get_settings

logger = logging.getLogger("ccprism.auth")
_jwt = JsonWebToken(["HS256"])


def is_loopback_host(host: str) -> bool:
    """Do not resolve arbitrary hostnames when deciding whether access is local."""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_auth_settings(settings: GatewaySettings, host: str | None = None) -> None:
    """Fail closed on ambiguous, weak, or remotely exposed unauthenticated setups."""
    if settings.auth_enabled:
        if settings.auth_local_mode:
            raise ValueError("auth.local_mode must be false when authentication is enabled")
        if not (settings.gateway_master_key or settings.jwt_secret_key):
            raise ValueError("Configure auth.gateway_master_key or auth.jwt_secret_key")
        for name, value in (
            ("gateway_master_key", settings.gateway_master_key),
            ("jwt_secret_key", settings.jwt_secret_key),
        ):
            if value and (len(value) < 32 or not value.strip()):
                raise ValueError(f"auth.{name} must contain at least 32 characters")
    elif not settings.auth_local_mode or not is_loopback_host(
        host if host is not None else settings.server.host
    ):
        raise ValueError("Unauthenticated access requires explicit local_mode and a loopback host")


async def verify_gateway_token(token: str) -> dict[str, Any] | None:
    """Validate an actual credential; local mode is never a token bypass."""
    settings = get_settings()
    if not token:
        return None
    if settings.gateway_master_key and hmac.compare_digest(
        token.encode(), settings.gateway_master_key.encode()
    ):
        return {"user": "master", "role": "admin"}
    if not settings.jwt_secret_key:
        return None
    try:
        claims = _jwt.decode(
            token,
            settings.jwt_secret_key,
            claims_options={"exp": {"essential": True}, "sub": {"essential": True}},
        )
        # Authlib accepts NaN NumericDate values; reject non-finite/bool dates.
        for name in ("exp", "iat", "nbf"):
            if name in claims:
                value = claims[name]
                if type(value) not in (int, float) or not math.isfinite(value):
                    return None
        claims.validate()
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            return None
        role = claims.get("role", "user")
        if role not in ("user", "admin"):
            return None
        return {"user": claims["sub"], "role": role}
    except Exception:
        # Token parser errors can contain credentials. Never include them in logs.
        logger.warning("Gateway token verification failed")
        return None


def _unauthorized() -> HTTPException:
    return HTTPException(
        401, "Invalid or missing gateway token", headers={"WWW-Authenticate": "Bearer"}
    )


async def require_gateway_user(request: Request) -> dict[str, Any]:
    """Authenticate before invoking endpoint or provider logic."""
    settings = get_settings()
    try:
        validate_auth_settings(settings)
    except ValueError as exc:
        raise HTTPException(503, "Gateway authentication is not configured securely") from exc

    if not settings.auth_enabled:
        # Also enforce the peer and Host at request time, including when started
        # through an external ASGI server instead of our CLI. No forwarded headers
        # are consulted here. Never put this opt-out mode behind a reverse proxy.
        if (
            request.client is None
            or not is_loopback_host(request.client.host)
            or not is_loopback_host(request.url.hostname or "")
            or request.headers.get("origin") is not None
            or request.headers.get("sec-fetch-site") is not None
        ):
            raise HTTPException(403, "Local mode only accepts non-browser loopback requests")
        return {"user": "local", "role": "admin"}

    api_keys = request.headers.getlist("x-api-key")
    authorizations = request.headers.getlist("authorization")
    if len(api_keys) > 1 or len(authorizations) > 1:
        raise _unauthorized()
    api_key = api_keys[0] if api_keys else None
    bearer = None
    if authorizations:
        scheme, separator, bearer = authorizations[0].partition(" ")
        if scheme.lower() != "bearer" or not separator or not bearer or bearer != bearer.strip():
            raise _unauthorized()
    if api_key is not None and bearer is not None and api_key != bearer:
        raise _unauthorized()
    principal = await verify_gateway_token(bearer or api_key or "")
    if principal is None:
        raise _unauthorized()
    return principal


async def require_gateway_admin(
    principal: Annotated[dict[str, Any], Depends(require_gateway_user)],
) -> dict[str, Any]:
    if principal["role"] != "admin":
        raise HTTPException(403, "Gateway administrator access required")
    return principal
