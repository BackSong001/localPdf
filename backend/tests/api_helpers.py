from __future__ import annotations

import io
import time

from PIL import Image


def image_bytes(
    size: tuple[int, int] = (100, 200),
    color=(255, 0, 0),
    image_format: str = "PNG",
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=image_format)
    return buffer.getvalue()


def upload(name: str, data: bytes, content_type: str = "image/png"):
    return ("files", (name, data, content_type))


def wait_for_job(client, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        if data["status"] in ("done", "error"):
            return data
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")
