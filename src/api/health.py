"""Minimal public liveness endpoint. Operational details require admin access."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
