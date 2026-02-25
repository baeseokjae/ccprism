"""Anthropic Messages API proxy endpoint."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger("ccprism.api.messages")

router = APIRouter()


@router.post("/v1/messages")
async def create_message(request: Request) -> Any:
    """Proxy Anthropic Messages API requests through LiteLLM Router.

    Accepts requests in Anthropic Messages API format and routes them
    to the appropriate provider based on MD routing rules.
    """
    litellm_router = getattr(request.app.state, "litellm_router", None)
    if not litellm_router:
        raise HTTPException(status_code=503, detail="LiteLLM Router not initialized")

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    model = body.get("model", "claude-sonnet-4-6")
    messages = body.get("messages", [])
    stream = body.get("stream", False)

    # Build kwargs for LiteLLM
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }

    # Forward supported parameters
    for param in (
        "max_tokens",
        "temperature",
        "top_p",
        "top_k",
        "stop_sequences",
        "system",
        "tools",
        "tool_choice",
        "thinking",
        "metadata",
    ):
        if param in body:
            kwargs[param] = body[param]

    # Pass original request info for routing decisions
    kwargs["request_kwargs"] = {
        "tools": body.get("tools", []),
        "thinking": body.get("thinking", {}),
    }

    try:
        if stream:
            return StreamingResponse(
                _stream_response(litellm_router, kwargs),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            response = await litellm_router.acompletion(**kwargs)
            return _format_anthropic_response(response)

    except Exception as e:
        logger.error(f"Request failed: {e}")
        raise HTTPException(status_code=502, detail=f"Provider request failed: {e}") from e


async def _stream_response(router: Any, kwargs: dict) -> Any:
    """Stream response as Server-Sent Events in Anthropic format."""
    kwargs["stream"] = True
    try:
        response = await router.acompletion(**kwargs)
        async for chunk in response:
            data = _format_stream_chunk(chunk)
            if data:
                yield f"event: content_block_delta\ndata: {json.dumps(data)}\n\n"

        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

    except Exception as e:
        error_data = {"type": "error", "error": {"type": "api_error", "message": str(e)}}
        yield f"event: error\ndata: {json.dumps(error_data)}\n\n"


def _format_anthropic_response(response: Any) -> dict:
    """Format LiteLLM response to Anthropic Messages API format."""
    choices = getattr(response, "choices", [])
    content = []

    if choices:
        message = choices[0].message
        if hasattr(message, "content") and message.content:
            content.append({"type": "text", "text": message.content})
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.function.name,
                        "input": json.loads(tc.function.arguments)
                        if isinstance(tc.function.arguments, str)
                        else tc.function.arguments,
                    }
                )

    return {
        "id": getattr(response, "id", "msg_unknown"),
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": getattr(response, "model", "unknown"),
        "stop_reason": _map_stop_reason(choices[0].finish_reason if choices else None),
        "usage": {
            "input_tokens": getattr(response.usage, "prompt_tokens", 0)
            if hasattr(response, "usage")
            else 0,
            "output_tokens": getattr(response.usage, "completion_tokens", 0)
            if hasattr(response, "usage")
            else 0,
        },
    }


def _format_stream_chunk(chunk: Any) -> dict | None:
    """Format a streaming chunk to Anthropic format."""
    choices = getattr(chunk, "choices", [])
    if not choices:
        return None

    delta = choices[0].delta
    if hasattr(delta, "content") and delta.content:
        return {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": delta.content},
        }
    return None


def _map_stop_reason(finish_reason: str | None) -> str:
    """Map OpenAI finish_reason to Anthropic stop_reason."""
    mapping = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "content_filter": "end_turn",
    }
    return mapping.get(finish_reason or "", "end_turn")
