from __future__ import annotations

from fastapi import APIRouter, Request

from app.errors import AppError
from app.services.llm import summarize_text

router = APIRouter(prefix="/api/summarize", tags=["summarize"])


@router.post("")
async def summarize(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise AppError("INVALID_REQUEST", "JSON 형식이 올바르지 않습니다.") from None

    if not isinstance(body, dict):
        raise AppError("INVALID_REQUEST")

    text = body.get("text", "")
    provider = body.get("provider")
    return summarize_text(text, request.app.state.settings, provider=provider)
