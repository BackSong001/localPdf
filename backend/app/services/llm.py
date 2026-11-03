from __future__ import annotations

import httpx

from app.errors import AppError
from app.settings import Settings


def summarize_text(
    text: str,
    settings: Settings,
    provider: str | None = None,
) -> dict[str, str]:
    cleaned_text = text.strip()
    if not cleaned_text:
        raise AppError("EMPTY_TEXT")

    chosen_provider = (provider or settings.llm_provider).lower()
    prompt = (
        "다음 문서를 읽고 핵심 내용을 체계적인 마크다운(Markdown) 목록과 요약으로 정리해 주세요:\n\n"
        f"{cleaned_text}"
    )

    if chosen_provider == "gemini":
        if not settings.gemini_api_keys:
            raise AppError("LLM_NOT_CONFIGURED", "Gemini API 키가 설정되지 않았습니다.")

        api_key = settings.gemini_api_keys[0]
        model = settings.gemini_model
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={api_key}"
        )
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ]
        }

        try:
            with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
                res = client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise AppError("LLM_UPSTREAM_ERROR", f"Gemini 통신 실패: {exc}") from None

        if res.status_code == 429:
            raise AppError("LLM_RATE_LIMITED")
        if res.status_code != 200:
            raise AppError("LLM_UPSTREAM_ERROR")

        data = res.json()
        try:
            summary = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            raise AppError("LLM_UPSTREAM_ERROR", "Gemini 응답 형식이 올바르지 않습니다.")

        return {
            "summary": summary,
            "provider": "gemini",
            "model": model,
        }

    elif chosen_provider == "nvidia":
        if not settings.nvidia_api_keys:
            raise AppError("LLM_NOT_CONFIGURED", "NVIDIA API 키가 설정되지 않았습니다.")

        api_key = settings.nvidia_api_keys[0]
        model = settings.nvidia_model
        url = f"{settings.nvidia_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
        }

        try:
            with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
                res = client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise AppError("LLM_UPSTREAM_ERROR", f"NVIDIA 통신 실패: {exc}") from None

        if res.status_code == 429:
            raise AppError("LLM_RATE_LIMITED")
        if res.status_code != 200:
            raise AppError("LLM_UPSTREAM_ERROR")

        data = res.json()
        try:
            summary = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            raise AppError("LLM_UPSTREAM_ERROR", "NVIDIA 응답 형식이 올바르지 않습니다.")

        return {
            "summary": summary,
            "provider": "nvidia",
            "model": model,
        }

    else:
        raise AppError("INVALID_REQUEST", f"지원하지 않는 LLM provider입니다: {chosen_provider}")
