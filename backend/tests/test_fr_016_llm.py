from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.llm import summarize_text
from app.settings import Settings


def test_tc_fr_016_a_summarize_unit_gemini() -> None:
    settings = Settings(
        llm_provider="gemini",
        gemini_api_keys=("test-gemini-key",),
        gemini_model="gemini-3.1-flash-lite",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "테스트 요약 결과입니다."}]
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_response):
        result = summarize_text("긴 원문 내용...", settings=settings, provider="gemini")
        assert result["summary"] == "테스트 요약 결과입니다."
        assert result["provider"] == "gemini"
        assert result["model"] == "gemini-3.1-flash-lite"
        # Secret key should never appear in output
        assert "test-gemini-key" not in str(result)


def test_tc_fr_016_b_key_not_configured() -> None:
    settings = Settings(
        llm_provider="gemini",
        gemini_api_keys=(),
    )
    app = create_app(settings)
    client = TestClient(app)

    res = client.post("/api/summarize", json={"text": "요약할 텍스트입니다."})
    assert res.status_code == 400
    data = res.json()
    assert data["detail"]["code"] == "LLM_NOT_CONFIGURED"


def test_tc_fr_016_c_empty_text() -> None:
    settings = Settings(
        llm_provider="gemini",
        gemini_api_keys=("test-key",),
    )
    app = create_app(settings)
    client = TestClient(app)

    res = client.post("/api/summarize", json={"text": "   "})
    assert res.status_code == 400
    data = res.json()
    assert data["detail"]["code"] == "EMPTY_TEXT"
