from __future__ import annotations

import shutil
import time
from pathlib import Path

import pymupdf

from app.services import pdf_ocr


class _FakeImage:
    width = 200
    height = 200


class _FakeTesseract:
    Output = type("Output", (), {"DICT": object()})

    @staticmethod
    def image_to_data(image, *, lang, output_type):
        assert isinstance(image, _FakeImage)
        assert lang == "kor"
        return {
            "text": ["OCR text"],
            "left": [20],
            "top": [30],
            "width": [80],
            "height": [20],
            "conf": ["95"],
        }


def test_add_pdf_text_layer_inserts_transparent_text(
    monkeypatch, make_image_only_pdf, tmp_path: Path
) -> None:
    source = make_image_only_pdf(tmp_path / "source.pdf", pages=1)
    output = tmp_path / "searchable.pdf"
    monkeypatch.setattr(pdf_ocr, "convert_from_path", lambda *args, **kwargs: [_FakeImage()])
    monkeypatch.setattr(pdf_ocr, "pytesseract", _FakeTesseract)

    pdf_ocr.add_pdf_text_layer(source, output, max_pages=10)

    with pymupdf.open(output) as document:
        assert document[0].get_text().strip().replace("\xa0", " ") == "OCR text"


def test_pdf_ocr_api_returns_searchable_pdf(
    client, monkeypatch, make_image_only_pdf, tmp_path: Path
) -> None:
    source = make_image_only_pdf(tmp_path / "source.pdf", pages=1)

    def fake_ocr(input_path: Path, output_path: Path, max_pages: int, **kwargs) -> Path:
        shutil.copyfile(input_path, output_path)
        return output_path

    monkeypatch.setattr("app.services.pdf_ocr_jobs.add_pdf_text_layer", fake_ocr)
    response = client.post(
        "/api/pdf/ocr",
        files={"file": ("source.pdf", source.read_bytes(), "application/pdf")},
    )

    assert response.status_code == 202
    created = response.json()
    assert created["status"] in {"queued", "converting", "done"}
    for _ in range(100):
        status = client.get(f"/api/pdf/ocr/{created['job_id']}").json()
        if status["status"] in {"done", "error"}:
            break
        time.sleep(0.01)

    assert status["status"] == "done"
    result = client.get(status["download_url"])
    assert result.status_code == 200
    with pymupdf.open(stream=result.content, filetype="pdf") as document:
        assert document.page_count == 1
