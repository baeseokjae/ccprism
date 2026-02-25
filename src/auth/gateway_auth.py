import logging

from ..config import get_settings

logger = logging.getLogger("ccprism.auth")


async def verify_gateway_token(token: str) -> dict | None:
    """LiteLLM custom_auth handler.

    Verifies the token sent by Claude Code in x-api-key header.
    Returns user info dict or None to reject.
    """
    settings = get_settings()

    # Local mode: accept any token
    if settings.auth_local_mode:
        return {"user": "local", "role": "admin"}

    # Master key check
    if settings.gateway_master_key and token == settings.gateway_master_key:
        return {"user": "master", "role": "admin"}

    # JWT verification
    try:
        from authlib.jose import jwt as jose_jwt

        claims = jose_jwt.decode(token, settings.jwt_secret_key)
        claims.validate()
        return {
            "user": claims.get("sub", "unknown"),
            "role": claims.get("role", "user"),
        }
    except Exception as e:
        logger.warning("Token verification failed: %s", e)
        return None
