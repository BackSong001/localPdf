from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.services.text import extract_pdf_text


def _pdf_upload(path: Path):
    return {"file": ("document.pdf", path.read_bytes(), "application/pdf")}


def _api_text(client, path: Path) -> dict:
    response = client.post("/api/pdf/text", files=_pdf_upload(path))
    assert response.status_code == 200, response.text
    return response.json()


def test_tc_fr_008_a_page_text_is_stripped(make_text_pdf, tmp_path: Path) -> None:
    path = make_text_pdf(tmp_path / "text.pdf", ["first page", "second page"])

    result = extract_pdf_text(path, max_pages=2000)

    assert [page.text for page in result.pages] == ["first page", "second page"]


def test_tc_fr_008_b_join_non_empty_pages(make_text_pdf, tmp_path: Path) -> None:
    path = make_text_pdf(tmp_path / "text.pdf", ["one", "", "three"])

    result = extract_pdf_text(path, max_pages=2000)

    assert result.text == "one\n\nthree"


def test_tc_fr_008_c_page_count_matches_pages(make_text_pdf, tmp_path: Path) -> None:
    path = make_text_pdf(tmp_path / "text.pdf", ["one", "two", "three"])

    result = extract_pdf_text(path, max_pages=2000)

    assert result.page_count == len(result.pages) == 3


def test_tc_fr_008_d_whitespace_only_page_is_empty(
    make_text_pdf, tmp_path: Path
) -> None:
    path = make_text_pdf(tmp_path / "text.pdf", ["   "])

    result = extract_pdf_text(path, max_pages=2000)

    assert result.pages[0].text == ""


def test_tc_fr_008_e_api_page_numbers_start_at_one(
    client, make_text_pdf, tmp_path: Path
) -> None:
    path = make_text_pdf(tmp_path / "text.pdf", ["one", "two"])

    body = _api_text(client, path)

    assert [page["page"] for page in body["pages"]] == [1, 2]
    assert body["has_text"] is True


def test_tc_fr_008_f_mixed_pdf_keeps_text_page_only(
    make_mixed_pdf, tmp_path: Path
) -> None:
    path = make_mixed_pdf(tmp_path / "mixed.pdf")

    result = extract_pdf_text(path, max_pages=2000)

    assert result.has_text is True
    assert result.pages[0].text == "text page"
    assert result.pages[1].text == ""


def test_tc_fr_009_a_image_only_pdf_returns_empty(
    client, make_image_only_pdf, tmp_path: Path
) -> None:
    path = make_image_only_pdf(tmp_path / "images.pdf", pages=2)

    body = _api_text(client, path)

    assert body["has_text"] is False
    assert body["text"] == ""
    assert body["pages"] == [
        {"page": 1, "text": ""},
        {"page": 2, "text": ""},
    ]


def test_tc_fr_009_b_mixed_pdf_has_text_and_empty_image_page(
    make_mixed_pdf, tmp_path: Path
) -> None:
    path = make_mixed_pdf(tmp_path / "mixed.pdf")

    result = extract_pdf_text(path, max_pages=2000)

    assert result.has_text is True
    assert result.text == "text page"
    assert result.pages[1].text == ""


def test_tc_fr_011_b_text_file_is_unsupported_pdf(client) -> None:
    response = client.post(
        "/api/pdf/text",
        files={"file": ("notes.pdf", b"hello", "application/pdf")},
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "UNSUPPORTED_PDF"


def test_tc_fr_011_c_corrupt_pdf_is_invalid(client) -> None:
    response = client.post(
        "/api/pdf/text",
        files={"file": ("broken.pdf", b"%PDF-1.7\nbroken", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_PDF"


def test_tc_fr_011_d_encrypted_pdf_is_invalid(
    client, make_encrypted_pdf, tmp_path: Path
) -> None:
    path = make_encrypted_pdf(tmp_path / "secret.pdf")

    response = client.post("/api/pdf/text", files=_pdf_upload(path))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_PDF"


def test_tc_fr_011_e_zero_page_pdf_is_invalid(client, tmp_path: Path) -> None:
    path = tmp_path / "empty.pdf"
    document = pymupdf.open()
    document.save(str(path))
    document.close()

    response = client.post("/api/pdf/text", files=_pdf_upload(path))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_PDF"


def test_tc_fr_011_f_too_many_pages(client_factory, make_text_pdf, tmp_path: Path) -> None:
    path = make_text_pdf(tmp_path / "many.pdf", ["one", "two", "three"])

    with client_factory(max_pdf_pages=2) as client:
        response = client.post("/api/pdf/text", files=_pdf_upload(path))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PDF_TOO_MANY_PAGES"


def test_tc_fr_011_g_pdf_too_large(client_factory, make_text_pdf, tmp_path: Path) -> None:
    path = make_text_pdf(tmp_path / "doc.pdf", ["one"])

    with client_factory(max_pdf_bytes=10) as client:
        response = client.post("/api/pdf/text", files=_pdf_upload(path))

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "PDF_TOO_LARGE"


def test_tc_fr_011_i_pdf_magic_is_required(client) -> None:
    response = client.post(
        "/api/pdf/text",
        files={"file": ("notes.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "UNSUPPORTED_PDF"


def test_tc_api_005_text_response_schema(client, make_text_pdf, tmp_path: Path) -> None:
    path = make_text_pdf(tmp_path / "text.pdf", ["hello"])

    body = _api_text(client, path)

    assert set(body) == {"page_count", "has_text", "text", "pages"}
    assert isinstance(body["page_count"], int)
    assert isinstance(body["has_text"], bool)
    assert isinstance(body["text"], str)
    assert isinstance(body["pages"], list)


def test_tc_fr_015_a_text_error_shape(client) -> None:
    response = client.post(
        "/api/pdf/text",
        files={"file": ("notes.pdf", b"hello", "application/pdf")},
    )

    detail = response.json()["detail"]
    assert set(detail) == {"code", "message"}
    assert detail["code"] == "UNSUPPORTED_PDF"


@pytest.mark.parametrize("pages", [["one"], ["one", "two"]])
def test_text_extraction_page_count_is_stable(
    make_text_pdf, tmp_path: Path, pages: list[str]
) -> None:
    path = make_text_pdf(tmp_path / "text.pdf", pages)

    result = extract_pdf_text(path, max_pages=2000)

    assert result.page_count == len(pages)
