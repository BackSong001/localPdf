from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest

from app.services.pdf_builder import build_pdf
from tests.api_helpers import image_bytes, upload, wait_for_job
from tests.helpers import center_pixel, extract_page_image


def _page_count(content: bytes) -> int:
    with pymupdf.open(stream=content, filetype="pdf") as document:
        return document.page_count


def _uploaded_names(root: Path) -> list[str]:
    return sorted(path.name for path in root.glob("localpdf-*/uploads/*"))


def test_tc_fr_001_a_upload_convert_and_download(client) -> None:
    files = [
        upload(f"{index}.png", image_bytes(color=(index * 80, 0, 0)))
        for index in range(3)
    ]

    response = client.post("/api/jobs", files=files)
    assert response.status_code == 202
    created = response.json()
    assert created["total"] == 3
    assert created["status"] == "queued"
    assert created["processed"] == 0
    assert created["download_url"] is None

    finished = wait_for_job(client, created["job_id"])
    assert finished["status"] == "done"
    assert finished["processed"] == 3
    assert finished["download_url"] == f"/api/jobs/{created['job_id']}/download"

    download = client.get(finished["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert "attachment" in download.headers["content-disposition"]
    assert _page_count(download.content) == 3


def test_tc_fr_001_b_empty_upload(client) -> None:
    response = client.post("/api/jobs")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EMPTY_UPLOAD"


def test_tc_fr_001_c_too_many_files(client_factory, tmp_path: Path) -> None:
    with client_factory(max_files=2) as client:
        files = [
            upload(f"{index}.png", image_bytes()) for index in range(3)
        ]
        response = client.post("/api/jobs", files=files)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TOO_MANY_FILES"
    assert list(tmp_path.glob("localpdf-*")) == []


def test_tc_fr_001_d_file_too_large(client_factory, tmp_path: Path) -> None:
    with client_factory(max_image_bytes=10) as client:
        response = client.post(
            "/api/jobs",
            files=[upload("big.png", image_bytes())],
        )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"
    assert list(tmp_path.glob("localpdf-*")) == []


def test_tc_fr_001_e_total_size_exceeded(client_factory, tmp_path: Path) -> None:
    with client_factory(max_total_bytes=10) as client:
        response = client.post(
            "/api/jobs",
            files=[upload("one.png", image_bytes())],
        )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "TOTAL_SIZE_EXCEEDED"
    assert list(tmp_path.glob("localpdf-*")) == []


def test_tc_fr_001_f_unsupported_extension(client) -> None:
    response = client.post(
        "/api/jobs",
        files=[upload("photo.heic", b"not really heic", "image/heic")],
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "UNSUPPORTED_IMAGE"


def test_tc_fr_001_g_corrupt_jpeg(client) -> None:
    response = client.post(
        "/api/jobs",
        files=[upload("broken.jpg", b"not an image", "image/jpeg")],
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_IMAGE"


def test_tc_fr_001_i_zero_byte_file(client) -> None:
    response = client.post(
        "/api/jobs",
        files=[upload("empty.jpg", b"", "image/jpeg")],
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_IMAGE"


def test_tc_fr_002_b_multipart_order_is_pdf_page_order(
    client, tmp_path: Path
) -> None:
    colors = [(0, 0, 255), (255, 0, 0), (0, 255, 0)]
    files = [
        upload(f"{index}.png", image_bytes(color=color))
        for index, color in enumerate(colors)
    ]
    created = client.post("/api/jobs", files=files).json()
    wait_for_job(client, created["job_id"])
    content = client.get(f"/api/jobs/{created['job_id']}/download").content
    pdf_path = tmp_path / "order.pdf"
    pdf_path.write_bytes(content)

    for index, expected in enumerate(colors):
        actual = center_pixel(extract_page_image(pdf_path, index))
        assert all(abs(actual[channel] - expected[channel]) <= 8 for channel in range(3))


def test_tc_fr_002_c_duplicate_filenames_keep_order(client, tmp_path: Path) -> None:
    files = [
        upload("same.png", image_bytes(color=(255, 0, 0))),
        upload("same.png", image_bytes(color=(0, 0, 255))),
    ]
    created = client.post("/api/jobs", files=files).json()
    wait_for_job(client, created["job_id"])
    content = client.get(f"/api/jobs/{created['job_id']}/download").content
    pdf_path = tmp_path / "duplicates.pdf"
    pdf_path.write_bytes(content)

    assert _page_count(content) == 2
    assert center_pixel(extract_page_image(pdf_path, 0))[0] > 200
    assert center_pixel(extract_page_image(pdf_path, 1))[2] > 200


def _slow_builder(uploads, output, normalized_dir, on_progress):
    def progress(count: int) -> None:
        on_progress(count)
        time.sleep(0.03)

    build_pdf(uploads, output, normalized_dir, progress)


def test_tc_fr_006_b_processed_is_monotonic(client_factory) -> None:
    with client_factory() as client:
        client.app.state.manager._builder = _slow_builder
        files = [
            upload(f"{index}.png", image_bytes(color=(index * 40, 0, 0)))
            for index in range(6)
        ]
        created = client.post("/api/jobs", files=files).json()
        seen: list[int] = []
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            body = client.get(f"/api/jobs/{created['job_id']}").json()
            seen.append(body["processed"])
            if body["status"] in ("done", "error"):
                break
            time.sleep(0.005)

    assert body["status"] == "done"
    assert seen == sorted(seen)
    assert body["processed"] == 6


def test_tc_fr_006_d_download_url_appears_only_when_done(client_factory) -> None:
    with client_factory() as client:
        client.app.state.manager._builder = _slow_builder
        created = client.post(
            "/api/jobs",
            files=[upload("a.png", image_bytes())],
        ).json()
        assert created["download_url"] is None
        finished = wait_for_job(client, created["job_id"])

    assert finished["status"] == "done"
    assert finished["download_url"] == f"/api/jobs/{created['job_id']}/download"


def test_tc_fr_007_b_download_before_done_is_conflict(client_factory) -> None:
    with client_factory() as client:
        client.app.state.manager._builder = _slow_builder
        created = client.post(
            "/api/jobs",
            files=[upload("a.png", image_bytes())],
        ).json()
        response = client.get(f"/api/jobs/{created['job_id']}/download")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "JOB_NOT_READY"


def test_tc_fr_007_c_download_unknown_job(client) -> None:
    response = client.get(f"/api/jobs/{uuid4().hex}/download")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "JOB_NOT_FOUND"


def test_tc_fr_007_d_download_failed_job_is_conflict(client_factory) -> None:
    def failing_builder(*_args, **_kwargs):
        raise RuntimeError("boom")

    with client_factory() as client:
        client.app.state.manager._builder = failing_builder
        created = client.post(
            "/api/jobs",
            files=[upload("a.png", image_bytes())],
        ).json()
        finished = wait_for_job(client, created["job_id"])
        response = client.get(f"/api/jobs/{created['job_id']}/download")

    assert finished["status"] == "error"
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "JOB_NOT_READY"


def test_tc_fr_007_e_expired_job_is_not_found(client_factory) -> None:
    with client_factory(job_ttl_seconds=1) as client:
        created = client.post(
            "/api/jobs",
            files=[upload("a.png", image_bytes())],
        ).json()
        wait_for_job(client, created["job_id"])
        time.sleep(1.05)
        response = client.get(f"/api/jobs/{created['job_id']}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "JOB_NOT_FOUND"


def test_tc_fr_012_e_validation_failure_removes_temp_dir(
    client, tmp_path: Path
) -> None:
    response = client.post(
        "/api/jobs",
        files=[upload("broken.jpg", b"not an image", "image/jpeg")],
    )

    assert response.status_code == 422
    assert list(tmp_path.glob("localpdf-*")) == []


def test_tc_fr_015_a_error_shape_and_korean_message(client) -> None:
    response = client.post("/api/jobs")

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "EMPTY_UPLOAD"
    assert any("\uac00" <= char <= "\ud7a3" for char in detail["message"])


def test_tc_fr_015_b_internal_error_hides_details(client_factory) -> None:
    with client_factory() as client:
        client.raise_server_exceptions = False

        def explode(*_args, **_kwargs):
            raise RuntimeError("secret internal detail")

        client.app.state.manager.create_job = explode
        response = client.post(
            "/api/jobs",
            files=[upload("a.png", image_bytes())],
        )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_ERROR"
    assert "secret internal detail" not in response.text


def test_tc_nfr_004_upload_filename_is_not_used_as_path(
    client, tmp_path: Path
) -> None:
    response = client.post(
        "/api/jobs",
        files=[upload("../../etc/passwd.jpg", image_bytes())],
    )

    assert response.status_code == 202
    assert _uploaded_names(tmp_path) == ["0000.jpg"]
    assert not (tmp_path / "etc").exists()


def test_tc_nfr_007_secret_is_not_in_response_or_logs(
    client_factory, caplog
) -> None:
    sentinel = "sentinel-secret-key"
    with client_factory(gemini_api_keys=(sentinel,)) as client:
        client.raise_server_exceptions = False
        client.app.state.manager.create_job = lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("boom")
        )
        response = client.post(
            "/api/jobs",
            files=[upload("a.png", image_bytes())],
        )

    assert sentinel not in response.text
    assert sentinel not in caplog.text


def test_tc_api_009_created_at_is_iso_utc(client) -> None:
    created = client.post(
        "/api/jobs",
        files=[upload("a.png", image_bytes())],
    ).json()

    created_at = created["created_at"]
    assert created_at.endswith("Z")
    datetime.fromisoformat(created_at)


def test_tc_api_010_wrong_multipart_field_is_empty_upload(client) -> None:
    response = client.post(
        "/api/jobs",
        files={"file": ("a.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EMPTY_UPLOAD"


@pytest.mark.slow
def test_tc_fr_001_h_exactly_1000_images(client_factory) -> None:
    with client_factory() as client:
        files = [
            upload(f"{index}.png", image_bytes(size=(10, 10)))
            for index in range(1000)
        ]
        response = client.post("/api/jobs", files=files)

    assert response.status_code == 202
    assert response.json()["total"] == 1000
