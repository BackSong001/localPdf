from __future__ import annotations

from pathlib import Path

import pymupdf

from app.services.pdf_builder import build_pdf

SAMPLE_IMAGE = Path(__file__).resolve().parents[2] / "test_data" / "1.jpg"


def test_tc_fr_017_a_searchable_pdf_layer(tmp_path: Path) -> None:
    output_pdf = tmp_path / "output.pdf"
    output_md = tmp_path / "output.md"

    build_pdf([SAMPLE_IMAGE], output_pdf, markdown_path=output_md, ocr=True)

    assert output_pdf.exists()
    assert output_md.exists()

    with pymupdf.open(str(output_pdf)) as doc:
        page = doc[0]
        extracted_text = page.get_text()
        assert len(extracted_text.strip()) > 0
        assert "1.3.1" in extracted_text


def test_tc_fr_017_b_markdown_generated(tmp_path: Path) -> None:
    output_pdf = tmp_path / "output.pdf"
    output_md = tmp_path / "output.md"

    build_pdf([SAMPLE_IMAGE], output_pdf, markdown_path=output_md, ocr=True)

    md_content = output_md.read_text(encoding="utf-8")
    assert "## Page 1" in md_content
    assert "1.3.1" in md_content


def test_tc_fr_017_c_ocr_disabled(tmp_path: Path) -> None:
    output_pdf = tmp_path / "output.pdf"

    build_pdf([SAMPLE_IMAGE], output_pdf, ocr=False)

    assert output_pdf.exists()
    with pymupdf.open(str(output_pdf)) as doc:
        page = doc[0]
        assert page.get_text().strip() == ""


def test_tc_fr_017_d_api_markdown_download(client) -> None:
    from tests.api_helpers import upload, wait_for_job

    image_content = SAMPLE_IMAGE.read_bytes()
    response = client.post("/api/jobs", files=[upload("1.jpg", image_content, "image/jpeg")])
    assert response.status_code == 202
    created = response.json()
    job = wait_for_job(client, created["job_id"], timeout=15.0)

    assert job["status"] == "done"
    assert job["markdown_url"] == f"/api/jobs/{job['job_id']}/markdown"

    res = client.get(job["markdown_url"])
    assert res.status_code == 200
    assert "text/markdown" in res.headers["content-type"]
    assert "1.3.1" in res.text


def test_tc_fr_017_e_api_ocr_can_be_disabled(client) -> None:
    from tests.api_helpers import upload, wait_for_job

    response = client.post(
        "/api/jobs",
        files=[upload("1.jpg", SAMPLE_IMAGE.read_bytes(), "image/jpeg")],
        data={"ocr": "false"},
    )
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["job_id"], timeout=15.0)

    assert job["status"] == "done"
    pdf = client.get(job["download_url"])
    assert pdf.status_code == 200
    with pymupdf.open(stream=pdf.content, filetype="pdf") as document:
        assert document[0].get_text().strip() == ""
